"""Compute keyword and vector match scores between jobs and the user profile."""
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jobtracker.config import settings
from jobtracker.db.models import Job, Match, UserProfile
from jobtracker.enrich.embedder import build_job_text
from jobtracker.enrich.reranker import rerank_pairs
from jobtracker.enrich.skills import skill_match_summary
from jobtracker.enrich.trim import build_rerank_query
from jobtracker.logging import get_logger
from jobtracker.metrics.prometheus import KEYWORD_SCORE, VECTOR_SCORE

log = get_logger(__name__)


async def compute_matches(session: AsyncSession, job_ids: list[int]) -> None:
    """Score a list of job IDs against all active profiles."""
    if not job_ids:
        return

    profiles_result = await session.execute(select(UserProfile))
    profiles = list(profiles_result.scalars().all())
    if not profiles:
        log.warning("matcher.no_profiles")
        return

    for profile in profiles:
        await _score_jobs_for_profile(session, job_ids, profile)


async def _score_jobs_for_profile(
    session: AsyncSession, job_ids: list[int], profile: UserProfile
) -> None:
    jobs_result = await session.execute(
        select(Job).where(Job.id.in_(job_ids), Job.embedding.isnot(None))
    )
    jobs = list(jobs_result.scalars().all())

    if not jobs:
        return

    profile_skills = _load_profile_skills(profile)
    profile_bio = _load_profile_bio(profile)
    # Short query for cross-encoder (full resume as query collapses RR near 0).
    rerank_query = build_rerank_query(profile_bio, profile_skills)

    rows: list[dict] = []
    for job in jobs:
        vector_score = await _vector_similarity(session, job.id, profile.id)  # type: ignore[arg-type]
        matched_skills, missing_skills, missing_master_skills, keyword_score = skill_match_summary(
            f"{job.title}\n{job.description_text or job.description_html or ''}",
            profile_skills,
            company_name=job.company,
        )
        KEYWORD_SCORE.observe(keyword_score)
        VECTOR_SCORE.observe(vector_score)
        rows.append({
            "job_id": job.id,
            "profile_id": profile.id,
            "keyword_score": keyword_score,
            "vector_score": vector_score,
            "rerank_score": None,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "missing_master_skills": missing_master_skills,
            "computed_at": datetime.utcnow(),
        })

    # Cross-encoder re-rank: top-K by vector vs short profile query (not full resume).
    if rows and rerank_query:
        ranked = sorted(
            range(len(rows)), key=lambda i: rows[i]["vector_score"], reverse=True
        )[: settings.reranker_top_k]
        docs = [
            build_job_text(jobs[i].title, jobs[i].company, jobs[i].description_text or "")
            for i in ranked
        ]
        scores = rerank_pairs(rerank_query, docs)
        for i, score in zip(ranked, scores):
            rows[i]["rerank_score"] = score

    if rows:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(Match).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["job_id", "profile_id"],
            set_={
                "keyword_score": stmt.excluded.keyword_score,
                "vector_score": stmt.excluded.vector_score,
                "rerank_score": stmt.excluded.rerank_score,
                "matched_skills": stmt.excluded.matched_skills,
                "missing_skills": stmt.excluded.missing_skills,
                "missing_master_skills": stmt.excluded.missing_master_skills,
                "computed_at": stmt.excluded.computed_at,
            },
        )
        await session.execute(stmt)
        log.info("matcher.scored", count=len(rows), profile_id=profile.id)


async def _vector_similarity(session: AsyncSession, job_id: int, profile_id: int) -> float:
    """Use pgvector <=> operator for cosine distance, convert to similarity."""
    result = await session.execute(
        text(
            "SELECT 1 - (j.embedding <=> p.embedding) AS cosine "
            "FROM jobs j, user_profile p "
            "WHERE j.id = :job_id AND p.id = :profile_id"
        ),
        {"job_id": job_id, "profile_id": profile_id},
    )
    row = result.fetchone()
    if not row:
        return 0.0
    return max(0.0, float(row[0]))


def _load_profile_skills(profile: UserProfile) -> list[str]:
    skills = profile.profile_json.get("skills", [])
    return skills if isinstance(skills, list) else []


def _load_profile_bio(profile: UserProfile) -> str:
    bio = profile.profile_json.get("bio", "")
    return bio if isinstance(bio, str) else ""
