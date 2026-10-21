"""Integration test: matcher SQL with real pgvector (task 37).

Verifies that compute_matches() correctly uses pgvector's <=> operator
to score jobs against a user profile on a live Postgres with pgvector.
No sentence-transformers model needed — we use hand-crafted unit vectors
so the expected cosine values are known exactly.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from jobtracker.db.engine import get_session, init_db
from jobtracker.db.models import Job, Source, UserProfile
from jobtracker.enrich.matcher import compute_matches

pytestmark = pytest.mark.integration

_TEST_ATS = "test-matcher"
_DIM = 384


def _unit_vec(index: int) -> list[float]:
    """384-dim unit vector with 1.0 at position `index`, rest 0."""
    v = [0.0] * _DIM
    v[index] = 1.0
    return v


@pytest_asyncio.fixture
async def matcher_rows() -> dict:
    """Insert source, two jobs with embeddings, and a user profile. Yield IDs. Cleanup after."""
    await init_db()

    profile_vec = _unit_vec(0)     # basis vector e0
    similar_vec = _unit_vec(0)     # identical to profile  → cosine = 1.0
    dissimilar_vec = _unit_vec(1)  # orthogonal to profile → cosine = 0.0

    source_id: int | None = None
    profile_id: int | None = None
    similar_id: int | None = None
    dissimilar_id: int | None = None

    try:
        async with get_session() as session:
            source = Source(
                ats=_TEST_ATS,
                company_slug="matcher-co",
                company_name="MatcherCo",
                base_url="https://example.test/matcher",
            )
            session.add(source)
            await session.flush()
            source_id = source.id

            similar_job = Job(
                source_id=source_id,
                external_id="MATCH-SIM",
                canonical_hash=b"\x00" * 8,
                content_hash=b"\x01" * 8,
                title="Data Engineer",
                company="MatcherCo",
                apply_url="https://example.test/apply/sim",
                description_text="Python SQL dbt Airflow Spark data engineering",
                embedding=similar_vec,
            )
            dissimilar_job = Job(
                source_id=source_id,
                external_id="MATCH-DIS",
                canonical_hash=b"\x02" * 8,
                content_hash=b"\x03" * 8,
                title="Frontend Engineer",
                company="MatcherCo",
                apply_url="https://example.test/apply/dis",
                description_text="React TypeScript CSS JavaScript frontend",
                embedding=dissimilar_vec,
            )
            session.add(similar_job)
            session.add(dissimilar_job)
            await session.flush()
            similar_id = similar_job.id
            dissimilar_id = dissimilar_job.id

            profile = UserProfile(
                name="test-matcher-profile",
                profile_json={"skills": ["Python", "SQL", "dbt", "Airflow", "Spark"]},
                embedding=profile_vec,
            )
            session.add(profile)
            await session.flush()
            profile_id = profile.id

        yield {
            "source_id": source_id,
            "similar_id": similar_id,
            "dissimilar_id": dissimilar_id,
            "profile_id": profile_id,
        }

    finally:
        # user_profile DELETE cascades to matches
        if profile_id is not None:
            async with get_session() as session:
                await session.execute(
                    text("DELETE FROM user_profile WHERE id = :pid"),
                    {"pid": profile_id},
                )
        if source_id is not None:
            async with get_session() as session:
                await session.execute(
                    text("DELETE FROM jobs WHERE source_id = :sid"),
                    {"sid": source_id},
                )
                await session.execute(
                    text("DELETE FROM sources WHERE id = :sid"),
                    {"sid": source_id},
                )


async def test_compute_matches_creates_rows(matcher_rows: dict) -> None:
    """compute_matches() produces one Match row per job."""
    async with get_session() as session:
        await compute_matches(session, [matcher_rows["similar_id"], matcher_rows["dissimilar_id"]])

    async with get_session() as session:
        count = (
            await session.execute(
                text("SELECT COUNT(*) FROM matches WHERE profile_id = :pid"),
                {"pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
    assert count == 2


async def test_identical_embedding_yields_max_vector_score(matcher_rows: dict) -> None:
    """Job whose embedding equals the profile gets vector_score ≈ 1.0."""
    async with get_session() as session:
        await compute_matches(session, [matcher_rows["similar_id"]])

    async with get_session() as session:
        score = (
            await session.execute(
                text(
                    "SELECT vector_score FROM matches "
                    "WHERE job_id = :jid AND profile_id = :pid"
                ),
                {"jid": matcher_rows["similar_id"], "pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
    assert score >= 0.99


async def test_orthogonal_embedding_yields_low_vector_score(matcher_rows: dict) -> None:
    """Job whose embedding is orthogonal to the profile gets vector_score ≈ 0.0."""
    async with get_session() as session:
        await compute_matches(session, [matcher_rows["dissimilar_id"]])

    async with get_session() as session:
        score = (
            await session.execute(
                text(
                    "SELECT vector_score FROM matches "
                    "WHERE job_id = :jid AND profile_id = :pid"
                ),
                {"jid": matcher_rows["dissimilar_id"], "pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
    assert score <= 0.1


async def test_similar_job_outranks_dissimilar_job(matcher_rows: dict) -> None:
    """Data engineering job scores higher than frontend job on the data engineer profile."""
    async with get_session() as session:
        await compute_matches(session, [matcher_rows["similar_id"], matcher_rows["dissimilar_id"]])

    async with get_session() as session:
        sim_score = (
            await session.execute(
                text("SELECT vector_score FROM matches WHERE job_id = :jid AND profile_id = :pid"),
                {"jid": matcher_rows["similar_id"], "pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
        dis_score = (
            await session.execute(
                text("SELECT vector_score FROM matches WHERE job_id = :jid AND profile_id = :pid"),
                {"jid": matcher_rows["dissimilar_id"], "pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
    assert sim_score > dis_score


async def test_keyword_score_reflects_profile_skills(matcher_rows: dict) -> None:
    """Job mentioning profile skills gets keyword_score > 0; frontend job gets lower."""
    async with get_session() as session:
        await compute_matches(session, [matcher_rows["similar_id"], matcher_rows["dissimilar_id"]])

    async with get_session() as session:
        sim_kw = (
            await session.execute(
                text("SELECT keyword_score FROM matches WHERE job_id = :jid AND profile_id = :pid"),
                {"jid": matcher_rows["similar_id"], "pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
        dis_kw = (
            await session.execute(
                text("SELECT keyword_score FROM matches WHERE job_id = :jid AND profile_id = :pid"),
                {"jid": matcher_rows["dissimilar_id"], "pid": matcher_rows["profile_id"]},
            )
        ).scalar_one()
    assert sim_kw > 0.0
    assert sim_kw > dis_kw
