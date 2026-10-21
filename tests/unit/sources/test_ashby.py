import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.ashby import AshbyAdapter

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "ashby_notion.json").read_text()
)

ADAPTER = AshbyAdapter(slug="notion", company_name="Notion")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_jobs() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 2
    assert not result.not_modified


@pytest.mark.asyncio
@respx.mock
async def test_parsed_job_fields() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "ashby-001"
    assert job.title == "Staff Data Engineer"
    assert job.company == "Notion"
    assert "ashbyhq.com" in job.apply_url
    assert job.seniority == "staff"
    assert job.remote is True


@pytest.mark.asyncio
@respx.mock
async def test_salary_from_compensation_block() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]
    assert job.salary_min == 170_000
    assert job.salary_max == 220_000
    assert job.salary_currency == "USD"


@pytest.mark.asyncio
@respx.mock
async def test_salary_falls_back_to_description_parse() -> None:
    # Second job has no compensation block — salary fields should be None.
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[1]
    assert job.salary_min is None
    assert job.salary_max is None


@pytest.mark.asyncio
@respx.mock
async def test_304_not_modified() -> None:
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"abc"')
    assert result.not_modified is True
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_etag_stored() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(
            200, json=FIXTURE, headers={"ETag": '"v1"'}
        )
    )
    result = await ADAPTER.fetch()
    assert result.etag == '"v1"'
