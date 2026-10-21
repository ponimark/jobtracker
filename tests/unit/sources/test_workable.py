import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.workable import WorkableAdapter

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "workable_acme.json").read_text()
)

ADAPTER = WorkableAdapter(slug="acme", company_name="Acme")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_jobs() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 2


@pytest.mark.asyncio
@respx.mock
async def test_parsed_fields() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "WK-ABC123"
    assert job.title == "Senior Data Engineer"
    assert job.company == "Acme"
    assert job.apply_url == "https://apply.workable.com/acme/j/WK-ABC123/"
    assert job.seniority == "senior"
    assert job.remote is True
    assert job.employment_type == "Full-time"


@pytest.mark.asyncio
@respx.mock
async def test_non_remote_job() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json=FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[1]
    assert job.external_id == "WK-DEF456"
    assert not job.remote  # is_remote returns None for clearly-onsite locations


@pytest.mark.asyncio
@respx.mock
async def test_304_not_modified() -> None:
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"tag"')
    assert result.not_modified is True


@pytest.mark.asyncio
@respx.mock
async def test_etag_roundtrip() -> None:
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(
            200, json=FIXTURE, headers={"ETag": '"wk-etag"'}
        )
    )
    result = await ADAPTER.fetch()
    assert result.etag == '"wk-etag"'
