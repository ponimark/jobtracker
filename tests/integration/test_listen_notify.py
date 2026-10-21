"""LISTEN/NOTIFY integration test (task 36).

Opens a direct asyncpg listener on the `new_job` channel, then inserts a Job
row through the ORM. The trigger installed by migration 0002_pgvector.py
fires `pg_notify('new_job', NEW.id::text)` and the listener should receive
the job's id within a short deadline.
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import asyncpg
import pytest
from sqlalchemy import text

from jobtracker.config import settings
from jobtracker.db.engine import get_session
from jobtracker.db.models import Job, Source

pytestmark = pytest.mark.integration


def _raw_dsn() -> str:
    return settings.database_url.replace("postgresql+asyncpg://", "postgresql://")


async def test_job_insert_triggers_notify(clean_test_rows: None) -> None:
    received: asyncio.Queue[int] = asyncio.Queue()

    listener = await asyncpg.connect(_raw_dsn())

    async def _on_notify(_conn, _pid, _channel, payload: str) -> None:
        await received.put(int(payload))

    try:
        await listener.add_listener("new_job", _on_notify)

        # Insert a Source + Job through the ORM to trip the trigger.
        async with get_session() as session:
            source = Source(
                ats="test-notify",
                company_slug="listen-co",
                company_name="ListenCo",
                base_url="https://example.test/listen-co",
            )
            session.add(source)
            await session.flush()
            source_id = source.id

            job = Job(
                source_id=source_id,
                external_id="N1",
                canonical_hash=b"\x00" * 16,
                content_hash=b"\x01" * 16,
                title="Data Engineer",
                company="ListenCo",
                apply_url="https://example.test/apply/N1",
                first_seen_at=datetime.utcnow(),
                last_seen_at=datetime.utcnow(),
            )
            session.add(job)
            await session.flush()
            expected_id = job.id

        # Trigger fires on COMMIT (end of get_session context). Give asyncpg a
        # beat to deliver the notification to the listener connection.
        job_id = await asyncio.wait_for(received.get(), timeout=5.0)
        assert job_id == expected_id
    finally:
        await listener.remove_listener("new_job", _on_notify)
        await listener.close()

        async with get_session() as session:
            await session.execute(
                text("DELETE FROM jobs WHERE source_id IN (SELECT id FROM sources WHERE ats = 'test-notify')")
            )
            await session.execute(text("DELETE FROM sources WHERE ats = 'test-notify'"))
