"""Per-source fetch → normalize → dedup → upsert pipeline."""
import time
from datetime import datetime

from jobtracker.db.engine import get_session
from jobtracker.db.models import FetchLog
from jobtracker.ingest.dedup import (
    filter_globally_new_external_ids,
    filter_new_external_ids,
    mark_seen,
)
from jobtracker.logging import get_logger
from jobtracker.metrics.prometheus import (
    FETCH_DURATION,
    NEW_JOBS_COUNTER,
    LAST_NEW_JOB_TS,
)
from jobtracker.normalize.experience import resolve_experience
from jobtracker.normalize.hashing import canonical_hash, content_hash
from jobtracker.normalize.title_filter import company_excluded, keep_for_detail_fetch, title_filter_reason
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter
from jobtracker.db.repo import (
    existing_external_ids,
    get_job_hashes,
    get_or_create_source,
    sync_job_aliases_for_hashes,
    update_source_poll_result,
    upsert_jobs,
    write_fetch_log,
)
log = get_logger(__name__)


async def run_source(adapter: SourceAdapter) -> None:
    """Fetch a single source and write new/changed jobs to the DB."""
    started_at = datetime.utcnow()
    t0 = time.monotonic()

    async with get_session() as session:
        source = await get_or_create_source(
            session,
            ats=adapter.ats,
            slug=adapter.slug,
            company_name=adapter.company_name,
            base_url=adapter.source_url,
        )
        source_id: int = source.id  # type: ignore[assignment]

    try:
        # Load stored ETag/Last-Modified
        async with get_session() as session:
            from sqlalchemy import select
            from jobtracker.db.models import Source as SourceModel
            result = await session.execute(
                select(SourceModel).where(SourceModel.id == source_id)
            )
            src = result.scalar_one()
            last_etag = src.last_etag
            last_modified = src.last_modified

        if adapter.supports_two_phase:
            fetch_result = await adapter.fetch_list(
                last_etag=last_etag, last_modified=last_modified
            )
            if not fetch_result.not_modified and fetch_result.jobs:
                all_ids = [j.external_id for j in fetch_result.jobs]
                new_ids = set(await filter_new_external_ids(source_id, all_ids))
                globally_new = set(await filter_globally_new_external_ids(all_ids))
                async with get_session() as session:
                    owned_here = set(
                        (await get_job_hashes(session, source_id, all_ids)).keys()
                    )
                    already_elsewhere = await existing_external_ids(session, all_ids)
                # New to this source, and not already stored under another source.
                new_ids = {
                    eid
                    for eid in new_ids
                    if eid in owned_here
                    or eid in globally_new
                    or eid not in already_elsewhere
                }
                jobs_needing_details = [
                    j for j in fetch_result.jobs if j.external_id in new_ids
                ]
                before_title = len(jobs_needing_details)
                # Keep soft SWE through detail fetch so JD rescue can run after.
                jobs_needing_details = [
                    j
                    for j in jobs_needing_details
                    if keep_for_detail_fetch(j.title, seniority=j.seniority)
                ]
                title_dropped = before_title - len(jobs_needing_details)
                if title_dropped:
                    log.info(
                        "worker.title_filtered",
                        ats=adapter.ats,
                        slug=adapter.slug,
                        dropped=title_dropped,
                        kept=len(jobs_needing_details),
                    )
                skipped_seen = len(fetch_result.jobs) - before_title
                if jobs_needing_details:
                    await adapter.fetch_details_for(jobs_needing_details)
                # Drop seen jobs from downstream processing so their existing
                # DB descriptions aren't overwritten by the empty ones we have
                # here. We still mark_seen() them below so Redis TTL refreshes.
                fetch_result = FetchResult(
                    jobs=jobs_needing_details,
                    status_code=fetch_result.status_code,
                    etag=fetch_result.etag,
                    last_modified=fetch_result.last_modified,
                )
                # Preserve the full id list for mark_seen TTL refresh.
                _two_phase_all_ids = all_ids
                log.debug(
                    "worker.two_phase",
                    ats=adapter.ats,
                    slug=adapter.slug,
                    total=len(all_ids),
                    new_with_details=len(jobs_needing_details),
                    skipped_seen=skipped_seen,
                    title_dropped=title_dropped,
                )
            else:
                _two_phase_all_ids = None
        else:
            fetch_result = await adapter.fetch(
                last_etag=last_etag, last_modified=last_modified
            )
            _two_phase_all_ids = None

        duration_ms = int((time.monotonic() - t0) * 1000)

        if fetch_result.not_modified:
            log.debug("worker.not_modified", ats=adapter.ats, slug=adapter.slug)
            async with get_session() as session:
                await update_source_poll_result(
                    session, source_id, status=304, failures_delta=0
                )
            return

        all_ids = [j.external_id for j in fetch_result.jobs]

        async with get_session() as session:
            existing_hashes = await get_job_hashes(session, source_id, all_ids)
            # Cross-source: Indeed ID already stored from another JobSpy search
            # query should not create a second jobs row.
            already_elsewhere = await existing_external_ids(session, all_ids)
            globally_new = set(await filter_globally_new_external_ids(all_ids))

        rows = []
        canonical_hashes: set[bytes] = set()
        title_dropped = 0
        cross_source_skipped = 0
        for job in fetch_result.jobs:
            if company_excluded(job.company):
                title_dropped += 1
                continue
            reason = title_filter_reason(
                job.title,
                seniority=job.seniority,
                description=job.description_text or job.description_html,
            )
            if reason is not None:
                title_dropped += 1
                continue
            owned_here = job.external_id in existing_hashes
            if (
                job.external_id in already_elsewhere
                and not owned_here
            ) or (
                job.external_id not in globally_new and not owned_here
            ):
                cross_source_skipped += 1
                continue
            experience = await resolve_experience(
                job.title,
                job.description_text,
                job.description_html,
                job.apply_url,
            )
            row = _to_db_row(job, source_id, experience)
            canonical_hashes.add(row["canonical_hash"])
            existing_hash = existing_hashes.get(job.external_id)
            if existing_hash is None or existing_hash != row["content_hash"]:
                rows.append(row)

        if title_dropped or cross_source_skipped:
            log.info(
                "worker.title_filtered",
                ats=adapter.ats,
                slug=adapter.slug,
                dropped=title_dropped,
                cross_source_skipped=cross_source_skipped,
                upsert_candidates=len(rows),
            )

        new_count = 0
        changed_count = 0

        if rows:
            async with get_session() as session:
                new_count, changed_count = await upsert_jobs(session, rows)

        if canonical_hashes:
            async with get_session() as session:
                await sync_job_aliases_for_hashes(session, list(canonical_hashes))

        # Mark all as seen in Redis. For two-phase adapters, use the full
        # list-page ids so TTL refreshes on jobs whose details we skipped.
        ids_for_seen = _two_phase_all_ids if _two_phase_all_ids is not None else all_ids
        if ids_for_seen:
            await mark_seen(source_id, ids_for_seen)

        # Update source metadata
        async with get_session() as session:
            await update_source_poll_result(
                session,
                source_id,
                status=fetch_result.status_code,
                etag=fetch_result.etag,
                last_modified=fetch_result.last_modified,
                failures_delta=0,
            )
            await write_fetch_log(
                session,
                FetchLog(
                    source_id=source_id,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status=fetch_result.status_code,
                    new_jobs=new_count,
                    changed_jobs=changed_count,
                ),
            )

        if new_count > 0:
            NEW_JOBS_COUNTER.labels(ats=adapter.ats).inc(new_count)
            LAST_NEW_JOB_TS.labels(source=f"{adapter.ats}/{adapter.slug}").set_to_current_time()

        FETCH_DURATION.labels(ats=adapter.ats, slug=adapter.slug).observe(duration_ms / 1000)

        log.info(
            "worker.done",
            ats=adapter.ats,
            slug=adapter.slug,
            new=new_count,
            changed=changed_count,
            total=len(fetch_result.jobs),
            duration_ms=duration_ms,
        )

    except Exception as exc:
        duration_ms = int((time.monotonic() - t0) * 1000)
        log.error("worker.error", ats=adapter.ats, slug=adapter.slug, error=str(exc))
        async with get_session() as session:
            await update_source_poll_result(
                session, source_id, status=0, failures_delta=1
            )
            await write_fetch_log(
                session,
                FetchLog(
                    source_id=source_id,
                    started_at=started_at,
                    duration_ms=duration_ms,
                    status=0,
                    error=str(exc)[:1000],
                ),
            )


def _to_db_row(job: NormalizedJob, source_id: int, experience) -> dict:
    return {
        "source_id": source_id,
        "external_id": job.external_id,
        "canonical_hash": canonical_hash(
            job.title,
            job.company,
            job.location,
            job.employment_type,
            job.seniority,
        ),
        "content_hash": content_hash(job.description_text or job.description_html),
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "remote": job.remote,
        "employment_type": job.employment_type,
        "seniority": job.seniority,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "salary_currency": job.salary_currency,
        "description_html": job.description_html,
        "description_text": job.description_text,
        "apply_url": job.apply_url,
        "posted_at": job.posted_at,
        "experience_min_years": experience.min_years,
        "experience_max_years": experience.max_years,
        "first_seen_at": datetime.utcnow(),
        "last_seen_at": datetime.utcnow(),
    }

