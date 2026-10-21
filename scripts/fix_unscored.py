"""Score the 123 jobs that have embeddings but no match row."""
import asyncio
import sys

sys.path.insert(0, "src")

from sqlalchemy import select, text

from jobtracker.db.engine import get_session
from jobtracker.db.models import Job
from jobtracker.enrich.matcher import compute_matches


async def main() -> None:
    async with get_session() as session:
        result = await session.execute(
            text("""
                SELECT id FROM jobs
                WHERE embedding IS NOT NULL
                AND removed_at IS NULL
                AND id NOT IN (SELECT DISTINCT job_id FROM matches)
                ORDER BY id
            """)
        )
        ids = [row[0] for row in result.fetchall()]

    print(f"Found {len(ids)} unscored jobs")

    if not ids:
        print("Nothing to do.")
        return

    batch_size = 100
    done = 0
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        async with get_session() as session:
            await compute_matches(session, chunk)
        done += len(chunk)
        print(f"Scored {done}/{len(ids)}...")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
