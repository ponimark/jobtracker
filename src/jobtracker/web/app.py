"""Simple FastAPI web UI for browsing matched jobs."""
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from sqlalchemy import func, or_, select, update

from jobtracker.db.engine import get_session
from jobtracker.db.models import Job, JobAlias, Match, UserProfile
from jobtracker.db.repo import get_canonical_group_sizes
from jobtracker.enrich.track_profiles import (
    ACTIVE_TRACKS,
    load_active_track_profiles,
    match_sort_key,
)
from jobtracker.normalize.cohort import (
    classify_cohort_timing,
    cohort_tag,
    is_new_grad_cohort,
    with_cohort_title_prefix,
)
from jobtracker.normalize.experience import parse_experience
from jobtracker.normalize.location import is_us_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.normalize.title_filter import company_excluded, load_title_filters, passes_title_filter, role_lane
from jobtracker.time import format_pacific, sort_pacific

app = FastAPI()

_templates = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=True,
)

# Fallback YOE for experience warnings when track resumes omit experience_years.
_DEFAULT_PROFILE_YEARS = 2


def _excluded_seniority_labels() -> set[str]:
    cfg = load_title_filters()
    labels = {str(x).strip().lower() for x in (cfg.get("exclude_seniority") or []) if x}
    # Always hide classic senior ladder on the board even if yaml omits them.
    return labels | {"senior", "staff", "director", "manager", "lead", "principal", "mid"}


@app.get("/", response_class=HTMLResponse)
async def index(limit: int = 5000, min_keyword: float = 0.0, min_vector: float = 0.0) -> HTMLResponse:
    async with get_session() as session:
        profiles = await load_active_track_profiles(session)
        if not profiles:
            # Fallback: any profile (legacy single-profile installs)
            legacy = await session.execute(
                select(UserProfile).order_by(UserProfile.updated_at.desc(), UserProfile.id.desc())
            )
            profiles = list(legacy.scalars().all())

        profile_ids = [p.id for p in profiles if p.id is not None]
        profile_by_id = {p.id: p for p in profiles if p.id is not None}
        profile_name = " + ".join(p.name for p in profiles) if profiles else "You"
        profile_years = _DEFAULT_PROFILE_YEARS
        for profile in profiles:
            experience_years = profile.profile_json.get("experience_years")
            if isinstance(experience_years, int):
                profile_years = experience_years
                break

        exclude_seniority = _excluded_seniority_labels()
        stmt = (
            select(Job, Match)
            .join(Match, Match.job_id == Job.id)
            .outerjoin(JobAlias, JobAlias.alias_job_id == Job.id)
            .where(JobAlias.alias_job_id.is_(None))
            .where(Job.removed_at.is_(None))
            .where(
                or_(
                    Job.seniority.is_(None),
                    Job.seniority.notin_(exclude_seniority),
                )
            )
            .order_by(func.coalesce(Job.posted_at, Job.first_seen_at).desc())
        )
        if profile_ids:
            stmt = stmt.where(Match.profile_id.in_(profile_ids))

        result = await session.execute(stmt)
        rows = result.fetchall()
        canonical_hashes = list({job.canonical_hash for job, _ in rows if job.canonical_hash is not None})
        group_sizes = await get_canonical_group_sizes(session, canonical_hashes)
        # Newest alias date per canonical job, so a fresh repost surfaces at the top.
        canon_ids = list({job.id for job, _ in rows})
        newest_alias: dict[int, datetime] = {}
        if canon_ids:
            alias_rows = await session.execute(
                select(
                    JobAlias.canonical_job_id,
                    func.max(func.coalesce(Job.posted_at, Job.first_seen_at)),
                )
                .join(Job, Job.id == JobAlias.alias_job_id)
                .where(JobAlias.canonical_job_id.in_(canon_ids))
                .where(Job.removed_at.is_(None))
                .group_by(JobAlias.canonical_job_id)
            )
            newest_alias = {cid: dt for cid, dt in alias_rows.fetchall() if dt is not None}

    # job_id -> list of (Job, Match, track)
    by_job: dict[int, list[tuple[Job, Match, str]]] = {}
    for job, match in rows:
        profile = profile_by_id.get(match.profile_id)
        track = (profile.name if profile else "UNKNOWN")
        by_job.setdefault(job.id, []).append((job, match, track))

    jobs = []
    for job_id, entries in by_job.items():
        job = entries[0][0]
        if company_excluded(job.company):
            continue
        if not is_us_location(job.location, job.description_text):
            continue
        if not passes_title_filter(
            job.title,
            seniority=job.seniority,
            description=job.description_text,
        ):
            continue

        track_scores: list[dict] = []
        for _, match, track in entries:
            if match.keyword_score < min_keyword or match.vector_score < min_vector:
                continue
            track_scores.append({
                "track": track,
                "keyword_score": match.keyword_score,
                "vector_score": match.vector_score,
                "rerank_score": match.rerank_score,
                "matched_skills": match.matched_skills or [],
                "missing_skills": match.missing_skills or [],
                "missing_master_skills": match.missing_master_skills or [],
                "sort_key": match_sort_key(
                    match.keyword_score, match.vector_score, match.rerank_score
                ),
            })
        if not track_scores:
            continue

        track_scores.sort(key=lambda row: row["sort_key"], reverse=True)
        best = track_scores[0]

        required_min, required_max = _job_experience(job)
        experience_warning = _experience_warning(required_min, profile_years)
        experience_bucket = _experience_bucket(required_min, required_max)
        cohort = classify_cohort_timing(job.title or "", job.description_text or "")
        cohort_timing = cohort["cohortTiming"]
        display_seniority = job.seniority
        if not display_seniority:
            inferred = infer_seniority(job.title or "")
            if inferred == "intern":
                display_seniority = "intern"
            elif is_new_grad_cohort(cohort_timing):
                display_seniority = "new_grad"
            elif cohort_timing == "early_career":
                display_seniority = "junior"
        is_intern = _is_intern(job, display_seniority)
        date_label, date_value, date_sort = _job_date(job)
        alias_dt = newest_alias.get(job.id)
        if alias_dt is not None and _sort_dt(alias_dt) > date_sort:
            date_label, date_value, date_sort = "Reposted", _format_dt(alias_dt), _sort_dt(alias_dt)
        jobs.append({
            "id": job.id,
            "title": with_cohort_title_prefix(job.title, cohort_timing),
            "raw_title": job.title,
            "company": job.company,
            "location": job.location or ("Remote" if job.remote else ""),
            "remote": bool(job.remote),
            "seniority": display_seniority,
            "cohort_timing": cohort_timing,
            "cohort_tag": cohort_tag(cohort_timing),
            "is_intern": is_intern,
            # Intern has its own Experience dropdown; keep New Grad for FT early talent.
            "is_new_grad": (not is_intern)
            and (
                is_new_grad_cohort(cohort_timing)
                or (display_seniority or "") in {"new_grad", "junior"}
            ),
            "role_lane": role_lane(job.title),
            "employment_type": job.employment_type,
            "apply_url": job.apply_url,
            "date_label": date_label,
            "date_value": date_value,
            "date_sort": date_sort,
            "applied_at": format_pacific(job.applied_at) if job.applied_at else None,
            "experience": _format_experience(required_min, required_max),
            "experience_bucket": experience_bucket,
            "experience_warning": experience_warning,
            "best_track": best["track"],
            "keyword_score": best["keyword_score"],
            "vector_score": best["vector_score"],
            "rerank_score": best["rerank_score"],
            "matched_skills": best["matched_skills"],
            "missing_skills": best["missing_skills"],
            "missing_master_skills": best["missing_master_skills"],
            "track_scores": track_scores,
            "merged_sources_count": group_sizes.get(job.canonical_hash, 1),
            "merged_sources_label": _merged_sources_label(group_sizes.get(job.canonical_hash, 1)),
        })

    # Newest first, then best combined score within the same day-ish ordering
    jobs.sort(
        key=lambda row: (row.get("date_sort") or "", row["keyword_score"]),
        reverse=True,
    )
    jobs = jobs[:limit]

    template = _templates.get_template("jobs.html")
    html = template.render(
        jobs=jobs,
        total=len(jobs),
        profile_name=profile_name,
        tracks=list(ACTIVE_TRACKS),
        updated=format_pacific(datetime.now(UTC)),
    )
    return HTMLResponse(
        html,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.post("/jobs/{job_id}/applied")
async def mark_job_applied(job_id: int) -> dict[str, str]:
    async with get_session() as session:
        result = await session.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        applied_at = datetime.utcnow()
        await session.execute(
            update(Job).where(Job.id == job_id).values(applied_at=applied_at)
        )

    return {"ok": "true", "applied_at": format_pacific(applied_at)}


def _format_experience(min_years: int | None, max_years: int | None) -> str | None:
    if min_years is None and max_years is None:
        return None
    if min_years is not None and max_years is not None:
        if min_years == max_years:
            return f"{min_years} years"
        return f"{min_years}-{max_years} years"
    if min_years is not None:
        return f"{min_years}+ years"
    return f"up to {max_years} years"


def _job_experience(job: Job) -> tuple[int | None, int | None]:
    if job.experience_min_years is not None or job.experience_max_years is not None:
        return job.experience_min_years, job.experience_max_years
    parsed = parse_experience(f"{job.title}\n{job.description_text or job.description_html or ''}")
    return parsed.min_years, parsed.max_years


def _experience_warning(required_min: int | None, profile_years: int | None) -> str | None:
    if required_min is None or profile_years is None:
        return None
    if profile_years >= required_min:
        return None
    return f"Needs {required_min}+ years"


def _is_intern(job: Job, display_seniority: str | None) -> bool:
    if (display_seniority or "").strip().lower() == "intern":
        return True
    if (job.seniority or "").strip().lower() == "intern":
        return True
    employment = (job.employment_type or "").strip().lower()
    if "intern" in employment:
        return True
    return infer_seniority(job.title or "") == "intern"


def _experience_bucket(min_years: int | None, max_years: int | None) -> str:
    if min_years is None and max_years is None:
        return "unstated"
    if max_years is not None and max_years <= 2:
        return "0-2"
    if min_years is not None and min_years <= 2:
        return "3-5"
    value = min_years if min_years is not None else max_years
    if value is None:
        return "unstated"
    if value <= 5:
        return "3-5"
    if value <= 8:
        return "6-8"
    return "9+"


def _job_date(job: Job) -> tuple[str, str | None, str]:
    if job.posted_at is not None:
        return "Posted", _format_dt(job.posted_at), _sort_dt(job.posted_at)
    if job.first_seen_at is not None:
        return "Seen", _format_dt(job.first_seen_at), _sort_dt(job.first_seen_at)
    return "Seen", None, ""


def _format_dt(value: datetime) -> str:
    return format_pacific(value)


def _sort_dt(value: datetime) -> str:
    return sort_pacific(value)


def _merged_sources_label(count: int) -> str | None:
    if count <= 1:
        return None
    return f"Merged from {count} postings"
