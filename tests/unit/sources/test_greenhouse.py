import json
from pathlib import Path

import pytest
import respx
import httpx

from jobtracker.sources.greenhouse import GreenhouseAdapter


FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "greenhouse_databricks.json").read_text()
)

ADAPTER = GreenhouseAdapter(slug="databricks", company_name="Databricks")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_jobs():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 2
    assert not result.not_modified


@pytest.mark.asyncio
@respx.mock
async def test_fetch_304_not_modified():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(304)
    )
    result = await ADAPTER.fetch(last_etag='"abc123"')
    assert result.not_modified is True
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_parsed_job_fields():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "12345"
    assert job.title == "Senior Data Engineer"
    assert job.company == "Databricks"
    assert "greenhouse.io" in job.apply_url
    assert job.seniority == "senior"
    assert job.remote is True  # "Remote, US"


@pytest.mark.asyncio
@respx.mock
async def test_salary_parsed_from_description():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]
    assert job.salary_min == 150_000
    assert job.salary_max == 200_000


@pytest.mark.asyncio
@respx.mock
async def test_etag_stored_in_result():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(
            200, json=FIXTURE, headers={"ETag": '"newetag"'}
        )
    )
    result = await ADAPTER.fetch()
    assert result.etag == '"newetag"'
