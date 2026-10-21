"""Mark existing jobs that fail title filters as removed (soft purge).

Run from E:\\job with Postgres up:
  .venv\\Scripts\\python.exe scripts\\purge_filtered_titles.py --dry-run
  .venv\\Scripts\\python.exe scripts\\purge_filtered_titles.py
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select, update

from jobtracker.db.engine import get_session
from jobtracker.db.models import Job
from jobtracker.normalize.title_filter import title_filter_reason


async def run(*, dry_run: bool, limit: int | None) -> None:
    async with get_session() as session:
        stmt = select(Job).where(Job.removed_at.is_(None)).order_by(Job.id)
        if limit:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        jobs = list(result.scalars().all())

    to_remove: list[tuple[int, str, str]] = []
    for job in jobs:
        reason = title_filter_reason(
            job.title,
            seniority=job.seniority,
            description=job.description_text,
        )
        if reason is not None:
            to_remove.append((job.id, job.title, reason))

    print(f"Scanned {len(jobs)} active jobs; {len(to_remove)} fail title filter")
    for job_id, title, reason in to_remove[:20]:
        print(f"  [{reason}] {job_id}: {title}")
    if len(to_remove) > 20:
        print(f"  ... +{len(to_remove) - 20} more")

    if dry_run or not to_remove:
        print("Dry-run only" if dry_run else "Nothing to purge")
        return

    ids = [job_id for job_id, _, _ in to_remove]
    now = datetime.utcnow()
    async with get_session() as session:
        await session.execute(
            update(Job).where(Job.id.in_(ids)).values(removed_at=now)
        )
        await session.commit()
    print(f"Marked removed_at on {len(ids)} jobs")


def main() -> int:
    parser = argparse.ArgumentParser(description="Soft-purge jobs that fail title filters")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
