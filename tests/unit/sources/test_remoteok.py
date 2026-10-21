import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.remoteok import RemoteOKAdapter

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "remoteok_sample.json").read_text()
)

ADAPTER = RemoteOKAdapter(slug="remoteok", company_name="RemoteOK")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_data_engineering_jobs_only() -> None:
    # Fixture has 3 jobs; only two match data-engineering keywords (frontend is dropped).
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 2
    assert all("frontend" not in j.title.lower() for j in result.jobs)


@pytest.mark.asyncio
@respx.mock
async def test_parsed_fields() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = next(j for j in result.jobs if j.external_id == "999001")

    assert job.title == "Senior Data Engineer"
    assert job.company == "Acme"
    assert job.apply_url == "https://remoteok.com/l/acme-senior-data-engineer"
    assert job.remote is True
    assert job.location == "Remote"
    assert job.seniority == "senior"
    assert job.salary_min == 150_000
    assert job.salary_max == 190_000


@pytest.mark.asyncio
@respx.mock
async def test_304_not_modified() -> None:
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"rok-tag"')
    assert result.not_modified is True
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_metadata_first_element_ignored() -> None:
    # Fixture's first element is metadata without 'id' — must not crash the parser.
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert all(j.external_id.isdigit() for j in result.jobs)
