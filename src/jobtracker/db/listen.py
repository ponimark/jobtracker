"""Postgres LISTEN/NOTIFY helper for the enricher process."""
import asyncio
from collections.abc import AsyncGenerator

import asyncpg

from jobtracker.config import settings
from jobtracker.logging import get_logger

log = get_logger(__name__)


async def listen_for_jobs(channel: str = "new_job") -> AsyncGenerator[int, None]:
    """
    Connect directly via asyncpg (bypasses SQLAlchemy) and yield job IDs
    as they arrive via NOTIFY. Reconnects automatically on connection loss.
    """
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    queue: asyncio.Queue[int] = asyncio.Queue()

    async def _connect_and_listen() -> None:
        while True:
            try:
                conn = await asyncpg.connect(dsn)
                log.info("listen.connected", channel=channel)

                async def _on_notify(
                    conn: asyncpg.Connection,
                    pid: int,
                    channel: str,
                    payload: str,
                ) -> None:
                    try:
                        await queue.put(int(payload))
                    except ValueError:
                        log.warning("listen.bad_payload", payload=payload)

                await conn.add_listener(channel, _on_notify)  # type: ignore[arg-type]

                # Keep the connection alive
                while not conn.is_closed():
                    await asyncio.sleep(30)
                    await conn.execute("SELECT 1")

                await conn.remove_listener(channel, _on_notify)  # type: ignore[arg-type]
                await conn.close()

            except (asyncpg.PostgresConnectionError, OSError) as exc:
                log.warning("listen.reconnecting", error=str(exc))
                await asyncio.sleep(5)

    # Start the listener loop in the background
    asyncio.create_task(_connect_and_listen())

    # Yield job IDs as they arrive
    while True:
        job_id = await queue.get()
        yield job_id
