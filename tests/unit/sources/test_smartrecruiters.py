import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.smartrecruiters import SmartRecruitersAdapter

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "smartrecruiters_acme.json").read_text()
)

ADAPTER = SmartRecruitersAdapter(slug="acme", company_name="Acme")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_jobs() -> None:
    # SmartRecruiters paginates; fixture has totalFound=1 so one page is enough.
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 1


@pytest.mark.asyncio
@respx.mock
async def test_parsed_fields() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "sr-42"
    assert job.title == "Senior Data Engineer"
    assert job.company == "Acme"
    assert "jobs.smartrecruiters.com/acme" in job.apply_url
    assert job.seniority == "senior"
    assert job.remote is True  # location.remote=true in fixture
    assert job.employment_type == "Permanent"


@pytest.mark.asyncio
@respx.mock
async def test_304_not_modified() -> None:
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"old"')
    assert result.not_modified is True
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_pagination_stops_when_offset_reaches_total() -> None:
    # With totalFound=1 and limit=100, the loop should not issue a second request.
    route = respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert len(result.jobs) == 1
    assert route.call_count == 1
