"""Integration test fixtures — require a live Postgres at settings.database_url.

Tests are skipped cleanly when the DB is unreachable so `pytest` still passes
in environments without the stack running (CI default, contributor laptop).
"""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from sqlalchemy import text

from jobtracker.config import settings
from jobtracker.db.engine import engine, get_session, init_db

TEST_ATS_PREFIX = "test-"


def _db_reachable() -> bool:
    # Plain TCP probe — avoids spinning up an event loop in a session fixture,
    # which breaks pytest-asyncio's per-test loop.
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    parsed = urlparse(dsn)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


@pytest.fixture(scope="session")
def db_available() -> bool:
    if os.environ.get("SKIP_INTEGRATION") == "1":
        return False
    return _db_reachable()


@pytest.fixture(autouse=True)
def _skip_if_no_db(request: pytest.FixtureRequest, db_available: bool) -> None:
    if not db_available:
        pytest.skip("integration DB not reachable at settings.database_url")


@pytest_asyncio.fixture(autouse=True)
async def _dispose_engine_per_test():
    """Module-level asyncpg pool is bound to the first event loop pytest-asyncio
    creates. Dispose after each test so the next test's fresh loop isn't using
    stale connections."""
    yield
    await engine.dispose()


@pytest_asyncio.fixture
async def clean_test_rows() -> None:
    """Remove any rows created by previous test runs under the test ATS prefix."""
    await init_db()
    async with get_session() as session:
        await session.execute(
            text(
                "DELETE FROM fetch_log "
                "WHERE source_id IN (SELECT id FROM sources WHERE ats LIKE :p)"
            ),
            {"p": f"{TEST_ATS_PREFIX}%"},
        )
        await session.execute(
            text(
                "DELETE FROM job_aliases "
                "WHERE alias_job_id IN ("
                "  SELECT j.id FROM jobs j JOIN sources s ON s.id = j.source_id "
                "  WHERE s.ats LIKE :p"
                ")"
            ),
            {"p": f"{TEST_ATS_PREFIX}%"},
        )
        await session.execute(
            text(
                "DELETE FROM jobs "
                "WHERE source_id IN (SELECT id FROM sources WHERE ats LIKE :p)"
            ),
            {"p": f"{TEST_ATS_PREFIX}%"},
        )
        await session.execute(
            text("DELETE FROM sources WHERE ats LIKE :p"),
            {"p": f"{TEST_ATS_PREFIX}%"},
        )
    yield
