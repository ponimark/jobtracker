"""Enricher process: LISTEN for new jobs → embed → match → notify."""
import asyncio

from sqlalchemy import update

from jobtracker.db.engine import get_session
from jobtracker.db.listen import listen_for_jobs
from jobtracker.db.models import Job
from jobtracker.db.repo import get_unembedded_jobs
from jobtracker.enrich.embedder import build_job_text, embed_jobs
from jobtracker.enrich.matcher import compute_matches
from jobtracker.logging import get_logger

log = get_logger(__name__)

_DEBOUNCE_S = 1.0
_BATCH_MAX = 64


async def run_enricher() -> None:
    """Entry point for the enricher process."""
    log.info("enricher.starting")

    # On startup, backfill any jobs that were inserted before enricher started
    await _backfill_unembedded()

    pending_ids: list[int] = []
    last_flush = asyncio.get_event_loop().time()

    async for job_id in listen_for_jobs("new_job"):
        pending_ids.append(job_id)
        now = asyncio.get_event_loop().time()

        should_flush = (
            len(pending_ids) >= _BATCH_MAX
            or (now - last_flush) >= _DEBOUNCE_S
        )

        if should_flush:
            ids_to_process = pending_ids[:]
            pending_ids.clear()
            last_flush = now
            asyncio.create_task(_process_batch(ids_to_process))


async def _process_batch(job_ids: list[int]) -> None:
    log.debug("enricher.processing", count=len(job_ids))

    async with get_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Job).where(Job.id.in_(job_ids), Job.embedding.is_(None))
        )
        jobs = list(result.scalars().all())

    if not jobs:
        return

    texts = [build_job_text(j.title, j.company, j.description_text or "") for j in jobs]
    vectors = embed_jobs(texts)

    async with get_session() as session:
        for job, vec in zip(jobs, vectors):
            from datetime import datetime
            await session.execute(
                update(Job)
                .where(Job.id == job.id)
                .values(embedding=vec, embedded_at=datetime.utcnow())
            )

    # Compute match scores
    async with get_session() as session:
        await compute_matches(session, [j.id for j in jobs])  # type: ignore[arg-type]

    log.info("enricher.batch_done", embedded=len(jobs))


async def _backfill_unembedded() -> None:
    """Process any jobs that don't have embeddings yet."""
    while True:
        async with get_session() as session:
            jobs = await get_unembedded_jobs(session, limit=100)

        if not jobs:
            break

        ids = [j.id for j in jobs]
        await _process_batch(ids)  # type: ignore[arg-type]
        log.info("enricher.backfill_batch", count=len(ids))
