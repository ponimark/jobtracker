import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.lever import LeverAdapter

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "lever_stripe.json").read_text()
)

ADAPTER = LeverAdapter(slug="stripe", company_name="Stripe")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_jobs():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert len(result.jobs) == 1
    assert not result.not_modified


@pytest.mark.asyncio
@respx.mock
async def test_parsed_fields():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "abc-123-def"
    assert job.title == "Senior Data Engineer"
    assert job.company == "Stripe"
    assert "lever.co" in job.apply_url
    assert job.remote is True
    assert job.employment_type == "Full-time"
    assert job.seniority == "senior"


@pytest.mark.asyncio
@respx.mock
async def test_salary_from_additional_plain():
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]
    assert job.salary_min == 160_000
    assert job.salary_max == 210_000


@pytest.mark.asyncio
@respx.mock
async def test_304_not_modified():
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"oldtag"')
    assert result.not_modified is True
