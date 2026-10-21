"""Re-score every embedded job against the current profile skill vocabulary."""
import asyncio
import sys

sys.path.insert(0, "src")

from sqlalchemy import text

from jobtracker.db.engine import get_session
from jobtracker.enrich.matcher import compute_matches


async def main() -> None:
    async with get_session() as session:
        result = await session.execute(
            text(
                "SELECT id FROM jobs "
                "WHERE embedding IS NOT NULL AND removed_at IS NULL "
                "ORDER BY id"
            )
        )
        ids = [row[0] for row in result.fetchall()]

    print(f"Re-scoring {len(ids)} jobs")
    if not ids:
        return

    batch_size = 200
    done = 0
    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        async with get_session() as session:
            await compute_matches(session, chunk)
        done += len(chunk)
        print(f"  {done}/{len(ids)}")
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
