"""End-to-end ingest pipeline test (tasks 34 + 35).

Uses a fake in-process adapter so we exercise the real worker, repo, dedup,
and upsert paths against a live Postgres — without needing HTTP mocking here
(respx coverage lives in tests/unit/sources/*).
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from jobtracker.db.engine import get_session
from jobtracker.ingest.worker import run_source
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

pytestmark = pytest.mark.integration


class _FakeAdapter(SourceAdapter):
    """In-process adapter that returns a pre-baked FetchResult each fetch()."""

    ats = "test-fake"

    def __init__(self, slug: str, results: list[FetchResult]) -> None:
        super().__init__(slug=slug, company_name="TestCo")
        self._results = list(results)
        self.calls = 0

    @property
    def source_url(self) -> str:
        return f"https://example.test/{self.slug}"

    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        self.calls += 1
        return self._results.pop(0)


def _job(ext: str, title: str = "Senior Data Engineer", desc: str = "build pipelines") -> NormalizedJob:
    return NormalizedJob(
        external_id=ext,
        title=title,
        company="TestCo",
        apply_url=f"https://example.test/apply/{ext}",
        description_html=f"<p>{desc}</p>",
        description_text=desc,
        location="Remote",
        remote=True,
        seniority="senior",
    )


async def _count_jobs(source_id: int) -> int:
    async with get_session() as session:
        result = await session.execute(
            text("SELECT COUNT(*) FROM jobs WHERE source_id = :sid"), {"sid": source_id}
        )
        return int(result.scalar_one())


async def _get_source_id(slug: str) -> int:
    async with get_session() as session:
        result = await session.execute(
            text("SELECT id FROM sources WHERE ats = 'test-fake' AND company_slug = :s"),
            {"s": slug},
        )
        return int(result.scalar_one())


async def test_first_ingest_creates_source_and_jobs(clean_test_rows: None) -> None:
    adapter = _FakeAdapter(
        slug="alpha",
        results=[FetchResult(jobs=[_job("A1"), _job("A2")], status_code=200, etag='"v1"')],
    )
    await run_source(adapter)

    source_id = await _get_source_id("alpha")
    assert await _count_jobs(source_id) == 2

    async with get_session() as session:
        row = (
            await session.execute(
                text("SELECT last_etag, last_status FROM sources WHERE id = :i"),
                {"i": source_id},
            )
        ).one()
    assert row.last_etag == '"v1"'
    assert row.last_status == 200


async def test_304_not_modified_is_noop(clean_test_rows: None) -> None:
    adapter = _FakeAdapter(
        slug="beta",
        results=[
            FetchResult(jobs=[_job("B1")], status_code=200, etag='"etag-beta"'),
            FetchResult(jobs=[], status_code=304, not_modified=True),
        ],
    )
    await run_source(adapter)
    await run_source(adapter)

    source_id = await _get_source_id("beta")
    assert await _count_jobs(source_id) == 1
    async with get_session() as session:
        status = (
            await session.execute(
                text("SELECT last_status FROM sources WHERE id = :i"), {"i": source_id}
            )
        ).scalar_one()
    assert status == 304


async def test_rerun_with_changed_content_updates_existing(clean_test_rows: None) -> None:
    adapter = _FakeAdapter(
        slug="gamma",
        results=[
            FetchResult(jobs=[_job("G1", desc="v1 description")], status_code=200),
            FetchResult(jobs=[_job("G1", desc="v2 description updated")], status_code=200),
        ],
    )
    await run_source(adapter)
    await run_source(adapter)

    source_id = await _get_source_id("gamma")
    assert await _count_jobs(source_id) == 1
    async with get_session() as session:
        desc = (
            await session.execute(
                text("SELECT description_text FROM jobs WHERE source_id = :i"),
                {"i": source_id},
            )
        ).scalar_one()
    assert desc == "v2 description updated"


async def test_fetch_exception_increments_failures(clean_test_rows: None) -> None:
    class _BrokenAdapter(_FakeAdapter):
        async def fetch(self, last_etag=None, last_modified=None):
            raise RuntimeError("network exploded")

    adapter = _BrokenAdapter(slug="delta", results=[])
    await run_source(adapter)

    source_id = await _get_source_id("delta")
    async with get_session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT consecutive_failures, last_status FROM sources WHERE id = :i"
                ),
                {"i": source_id},
            )
        ).one()
    assert row.consecutive_failures >= 1
    assert row.last_status == 0
    async with get_session() as session:
        err = (
            await session.execute(
                text(
                    "SELECT error FROM fetch_log WHERE source_id = :i ORDER BY id DESC LIMIT 1"
                ),
                {"i": source_id},
            )
        ).scalar_one()
    assert "network exploded" in err
