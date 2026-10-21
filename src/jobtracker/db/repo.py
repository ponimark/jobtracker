from datetime import datetime
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from jobtracker.db.models import FetchLog, Job, JobAlias, Match, Source
from jobtracker.logging import get_logger

log = get_logger(__name__)


async def get_or_create_source(session: AsyncSession, ats: str, slug: str, **kwargs: Any) -> Source:
    result = await session.execute(
        select(Source).where(Source.ats == ats, Source.company_slug == slug)
    )
    source = result.scalar_one_or_none()
    if source is None:
        source = Source(ats=ats, company_slug=slug, **kwargs)
        session.add(source)
        await session.flush()
    return source


async def upsert_jobs(session: AsyncSession, rows: list[dict[str, Any]]) -> tuple[int, int]:
    """Batch upsert jobs. Returns (new_count, changed_count)."""
    if not rows:
        return 0, 0

    stmt = insert(Job).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["source_id", "external_id"],
        set_={
            "last_seen_at": stmt.excluded.last_seen_at,
            "content_hash": stmt.excluded.content_hash,
            "canonical_hash": stmt.excluded.canonical_hash,
            "title": stmt.excluded.title,
            "company": stmt.excluded.company,
            "apply_url": stmt.excluded.apply_url,
            "description_html": stmt.excluded.description_html,
            "description_text": stmt.excluded.description_text,
            "salary_min": stmt.excluded.salary_min,
            "salary_max": stmt.excluded.salary_max,
            "location": stmt.excluded.location,
            "remote": stmt.excluded.remote,
            "employment_type": stmt.excluded.employment_type,
            "seniority": stmt.excluded.seniority,
        },
        where=Job.content_hash != stmt.excluded.content_hash,
    ).returning(Job.id, text("(xmax = 0) AS is_insert"))

    result = await session.execute(stmt)
    rows_returned = result.fetchall()
    new_count = sum(1 for _, is_insert in rows_returned if is_insert)
    changed_count = len(rows_returned) - new_count
    return new_count, changed_count


async def get_job_hashes(
    session: AsyncSession,
    source_id: int,
    external_ids: list[str],
) -> dict[str, bytes]:
    """Return existing content hashes for the given source/external IDs."""
    if not external_ids:
        return {}

    result = await session.execute(
        select(Job.external_id, Job.content_hash).where(
            Job.source_id == source_id,
            Job.external_id.in_(external_ids),
        )
    )
    return {external_id: content_hash for external_id, content_hash in result.fetchall()}


async def existing_external_ids(
    session: AsyncSession,
    external_ids: list[str],
) -> set[str]:
    """Return external_ids that already exist on any source (cross-source dedupe)."""
    if not external_ids:
        return set()
    result = await session.execute(
        select(Job.external_id).where(Job.external_id.in_(external_ids)).distinct()
    )
    return {row[0] for row in result.fetchall() if row[0]}


# Lower = better primary when collapsing multi-city / multi-source dupes.
_ATS_PRIMARY_RANK = {
    "greenhouse": 0,
    "lever": 0,
    "ashby": 0,
    "workable": 1,
    "smartrecruiters": 1,
    "icims": 2,
    "workday": 2,
    "indeed": 5,
    "adzuna": 6,
}


def _ats_primary_rank(ats: str | None) -> int:
    return _ATS_PRIMARY_RANK.get((ats or "").lower(), 4)


async def sync_job_aliases_for_hashes(session: AsyncSession, canonical_hashes: list[bytes]) -> int:
    """Create or refresh alias mappings for all jobs that share the given canonical hashes."""
    if not canonical_hashes:
        return 0

    # Prefer direct ATS apply URLs over aggregator spam; then score; then age.
    result = await session.execute(
        select(
            Job.id,
            Job.canonical_hash,
            Job.first_seen_at,
            Job.removed_at,
            Source.ats,
            func.max(Match.keyword_score + Match.vector_score).label("score"),
        )
        .join(Source, Source.id == Job.source_id)
        .outerjoin(Match, Match.job_id == Job.id)
        .where(Job.canonical_hash.in_(canonical_hashes))
        .group_by(Job.id, Job.canonical_hash, Job.first_seen_at, Job.removed_at, Source.ats)
    )
    rows = result.fetchall()
    if not rows:
        return 0

    groups: dict[bytes, list[tuple]] = defaultdict(list)
    for job_id, canonical_hash, first_seen_at, removed_at, ats, score in rows:
        groups[canonical_hash].append((job_id, first_seen_at, removed_at, ats, score))

    alias_ids = [job_id for job_id, *_ in rows]
    await session.execute(delete(JobAlias).where(JobAlias.alias_job_id.in_(alias_ids)))

    alias_rows: list[dict[str, Any]] = []
    for canonical_hash, members in groups.items():
        members.sort(
            key=lambda item: (
                0 if item[2] is None else 1,  # active over removed
                _ats_primary_rank(item[3]),
                0 if item[4] is not None else 1,
                -(float(item[4] or 0.0)),
                item[1],
                item[0],
            )
        )
        canonical_job_id = members[0][0]
        for alias_job_id, *_ in members[1:]:
            alias_rows.append(
                {
                    "alias_job_id": alias_job_id,
                    "canonical_job_id": canonical_job_id,
                    "canonical_hash": canonical_hash,
                    "created_at": datetime.utcnow(),
                }
            )

    if not alias_rows:
        return 0

    stmt = insert(JobAlias).values(alias_rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["alias_job_id"],
        set_={
            "canonical_job_id": stmt.excluded.canonical_job_id,
            "canonical_hash": stmt.excluded.canonical_hash,
            "created_at": stmt.excluded.created_at,
        },
    )
    await session.execute(stmt)
    return len(alias_rows)


async def get_canonical_group_sizes(session: AsyncSession, canonical_hashes: list[bytes]) -> dict[bytes, int]:
    """Return total posting counts for each canonical hash."""
    if not canonical_hashes:
        return {}

    result = await session.execute(
        select(
            Job.canonical_hash,
            func.count(Job.id).label("job_count"),
        )
        .where(Job.canonical_hash.in_(canonical_hashes))
        .group_by(Job.canonical_hash)
    )
    return {canonical_hash: int(job_count) for canonical_hash, job_count in result.fetchall()}


async def get_unembedded_jobs(session: AsyncSession, limit: int = 100) -> list[Job]:
    result = await session.execute(
        select(Job)
        .where(Job.embedding.is_(None), Job.removed_at.is_(None))
        .order_by(Job.first_seen_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_source_poll_result(
    session: AsyncSession,
    source_id: int,
    *,
    status: int,
    etag: str | None = None,
    last_modified: str | None = None,
    failures_delta: int = 0,
) -> None:
    values: dict[str, Any] = {
        "last_polled_at": datetime.utcnow(),
        "last_status": status,
    }
    if etag is not None:
        values["last_etag"] = etag
    if last_modified is not None:
        values["last_modified"] = last_modified
    if failures_delta > 0:
        values["consecutive_failures"] = Source.consecutive_failures + failures_delta
    else:
        values["consecutive_failures"] = 0

    await session.execute(update(Source).where(Source.id == source_id).values(**values))


async def write_fetch_log(session: AsyncSession, log_entry: FetchLog) -> None:
    session.add(log_entry)
    await session.flush()


async def get_enabled_sources(session: AsyncSession) -> list[Source]:
    result = await session.execute(select(Source).where(Source.enabled.is_(True)))
    return list(result.scalars().all())
