"""APScheduler-based adaptive poller for all sources."""
import asyncio
import random

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from jobtracker.config import settings
from jobtracker.ingest.worker import run_source
from jobtracker.logging import get_logger
from jobtracker.sources.base import SourceAdapter
from jobtracker.sources.registry import load_sources

log = get_logger(__name__)

_MAX_INTERVAL_S = 600  # 10 minutes cap for adaptive backoff


class AdaptiveScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._intervals: dict[str, int] = {}
        self._empty_streaks: dict[str, int] = {}

    def add_source(self, adapter: SourceAdapter, poll_interval_s: int) -> None:
        key = f"{adapter.ats}/{adapter.slug}"
        self._intervals[key] = poll_interval_s
        self._empty_streaks[key] = 0

        # Jitter start time so sources don't all fire at once, but cap at 60s
        # so long-interval sources (e.g. 4h aggregator searches) still fire shortly after
        # startup instead of being stranded for hours.
        start_delay = random.uniform(0, min(poll_interval_s, 60))

        self._scheduler.add_job(
            self._run_and_adapt,
            trigger=IntervalTrigger(seconds=poll_interval_s),
            args=[adapter, key],
            id=key,
            replace_existing=True,
            next_run_time=None,  # will be set after jitter delay
            misfire_grace_time=30,
        )

        # Schedule the jittered first run using a datetime (APScheduler requires it)
        def _trigger_now(job_key: str) -> None:
            from datetime import datetime, timezone
            self._scheduler.modify_job(job_key, next_run_time=datetime.now(timezone.utc))

        asyncio.get_event_loop().call_later(start_delay, _trigger_now, key)

        log.debug("scheduler.added", source=key, interval_s=poll_interval_s, start_delay_s=round(start_delay, 1))

    async def _run_and_adapt(self, adapter: SourceAdapter, key: str) -> None:
        from jobtracker.db.engine import get_session
        from jobtracker.db.repo import get_enabled_sources
        from sqlalchemy import select
        from jobtracker.db.models import Source as SourceModel, FetchLog as FetchLogModel

        await run_source(adapter)

        # Check recent new_jobs to adapt interval
        async with get_session() as session:
            result = await session.execute(
                select(FetchLogModel.new_jobs)
                .join(SourceModel, FetchLogModel.source_id == SourceModel.id)
                .where(
                    SourceModel.ats == adapter.ats,
                    SourceModel.company_slug == adapter.slug,
                )
                .order_by(FetchLogModel.started_at.desc())
                .limit(5)
            )
            recent = [row[0] for row in result.fetchall()]

        if recent and all(n == 0 for n in recent):
            self._empty_streaks[key] = self._empty_streaks.get(key, 0) + 1
            if self._empty_streaks[key] >= 5:
                current = self._intervals[key]
                new_interval = min(int(current * 1.5), _MAX_INTERVAL_S)
                if new_interval != current:
                    self._intervals[key] = new_interval
                    self._scheduler.reschedule_job(
                        key, trigger=IntervalTrigger(seconds=new_interval)
                    )
                    log.info("scheduler.backed_off", source=key, interval_s=new_interval)
        else:
            # Reset on any new jobs
            self._empty_streaks[key] = 0
            base = self._intervals.get(key, 60)
            # Only reset to base if we had backed off
            job = self._scheduler.get_job(key)
            if job and hasattr(job.trigger, "interval"):
                current_s = int(job.trigger.interval.total_seconds())
                if current_s > base:
                    self._intervals[key] = base
                    self._scheduler.reschedule_job(
                        key, trigger=IntervalTrigger(seconds=base)
                    )
                    log.info("scheduler.reset", source=key, interval_s=base)

    def start(self) -> None:
        self._scheduler.start()
        log.info("scheduler.started", sources=len(self._scheduler.get_jobs()))

    def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        log.info("scheduler.stopped")


async def run_ingestor() -> None:
    """Entry point for the ingestor process."""
    from jobtracker.db.engine import get_session
    from jobtracker.db.repo import get_or_create_source

    sources = load_sources(settings.sources_config)
    scheduler = AdaptiveScheduler()

    # Ensure all sources are registered in the DB
    async with get_session() as session:
        for adapter, _ in sources:
            await get_or_create_source(
                session,
                ats=adapter.ats,
                slug=adapter.slug,
                company_name=adapter.company_name,
                base_url=adapter.source_url,
            )

        # Disable any DB sources no longer in sources.yaml
        from sqlalchemy import update as sa_update
        from jobtracker.db.models import Source
        active_slugs = [adapter.slug for adapter, _ in sources]
        await session.execute(
            sa_update(Source)
            .where(Source.company_slug.notin_(active_slugs))
            .values(enabled=False)
        )
        log.info("ingestor.sync_sources", active=len(active_slugs))

    for adapter, interval in sources:
        scheduler.add_source(adapter, interval)

    scheduler.start()

    log.info("ingestor.running", source_count=len(sources))

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.stop()
