"""
Quick status check - DB stats, process state, top matches.
Run from E:/job:
    python scripts/status.py
"""
import asyncio
import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent / "src"))

from jobtracker.db.engine import get_session
from jobtracker.time import format_pacific
from sqlalchemy import text

from process_helpers import PROCESS_KEYWORDS, SERVICES, get_processes


def _is_running(name: str) -> bool:
    return bool(get_processes(SERVICES[name].keywords))


def _show_processes() -> None:
    processes = get_processes(PROCESS_KEYWORDS)
    if not processes:
        print("  No jobtracker processes found.")
        return
    for process in processes:
        print(f"ProcessId   : {process.get('ProcessId', '')}")
        print(f"CommandLine : {process.get('CommandLine', '')}")
        print()


async def main() -> None:
    ingestor_up = _is_running("ingestor")
    enricher_up = _is_running("enricher")

    print("\n=== Process Status ===")
    print(f"  Ingestor : {'RUNNING' if ingestor_up else 'STOPPED'}")
    print(f"  Enricher : {'RUNNING' if enricher_up else 'STOPPED'}")

    async with get_session() as session:
        total_jobs = (
            await session.execute(text("SELECT COUNT(*) FROM jobs WHERE removed_at IS NULL"))
        ).scalar()
        needs_embed = (
            await session.execute(text("SELECT COUNT(*) FROM jobs WHERE embedding IS NULL AND removed_at IS NULL"))
        ).scalar()
        needs_score = (
            await session.execute(
                text(
                    """
                    SELECT COUNT(*) FROM jobs
                    WHERE embedding IS NOT NULL AND removed_at IS NULL
                    AND id NOT IN (SELECT DISTINCT job_id FROM matches)
                    """
                )
            )
        ).scalar()
        scored_jobs = (await session.execute(text("SELECT COUNT(DISTINCT job_id) FROM matches"))).scalar()
        new_1h = (
            await session.execute(
                text("SELECT COUNT(*) FROM jobs WHERE first_seen_at > NOW() - INTERVAL '1 hour'")
            )
        ).scalar()
        new_24h = (
            await session.execute(
                text("SELECT COUNT(*) FROM jobs WHERE first_seen_at > NOW() - INTERVAL '24 hours'")
            )
        ).scalar()
        top = (
            await session.execute(
                text(
                    "SELECT j.title, j.company, "
                    "ROUND((m.vector_score * 0.7 + m.keyword_score * 0.3)::numeric, 2) AS score "
                    "FROM matches m JOIN jobs j ON j.id = m.job_id "
                    "ORDER BY score DESC LIMIT 5"
                )
            )
        ).fetchall()

    print("\n=== Database ===")
    print(f"  Total jobs    : {total_jobs:,}")
    print(f"  Scored jobs   : {scored_jobs:,}")
    print(f"  New (1h)      : {new_1h:,}")
    print(f"  New (24h)     : {new_24h:,}")

    print("\n=== Pipeline ===")
    if needs_embed == 0 and needs_score == 0:
        print("  All caught up!")
    if needs_embed > 0:
        print(f"  Needs embedding : {needs_embed:,}  -> run: python scripts\\enricher.py")
    if needs_score > 0:
        print(f"  Needs scoring   : {needs_score:,}  -> run: python scripts\\fix_unscored.py")

    # Log timestamps are Pacific (see jobtracker.logging._add_pacific_timestamp),
    # so the cutoff must also be rendered in Pacific for string comparison to work.
    cutoff = format_pacific(datetime.now(UTC) - timedelta(minutes=5), with_seconds=False)
    log_path = "ingestor.log"
    done_count = err_count = new_jobs = 0
    if os.path.exists(log_path):
        with open(log_path, "rb") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                    if record.get("timestamp", "") >= cutoff:
                        if record.get("event") == "worker.done":
                            done_count += 1
                            new_jobs += record.get("new", 0)
                        elif record.get("event") == "worker.error":
                            err_count += 1
                except Exception:
                    pass

    print("\n=== Ingestor (last 5 min) ===")
    print(f"  Sources polled : {done_count}")
    print(f"  New jobs found : {new_jobs}")
    print(f"  Errors         : {err_count}")

    if top:
        print("\n=== Top 5 Matches ===")
        for title, company, score in top:
            print(f"  {score}  {company} - {title}")

    print()


if __name__ == "__main__":
    if "--ps" in sys.argv:
        print("\n=== Running Processes ===")
        _show_processes()
        print()
    else:
        asyncio.run(main())
