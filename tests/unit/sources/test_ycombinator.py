import httpx
import pytest
import respx

from jobtracker.sources.ycombinator import YCombinatorAdapter

ADAPTER = YCombinatorAdapter(slug="workatastartup", company_name="YC Work at a Startup")

_FIXTURE = {
    "companies": [
        {
            "name": "DataStartup",
            "location": "San Francisco, CA",
            "jobs": [
                {
                    "id": 12345,
                    "title": "Data Engineer",
                    "description": "<p>We need a data engineer.</p>",
                    "location": "Remote",
                },
                {
                    "id": 12346,
                    "title": "Product Manager",
                    "description": "<p>PM role.</p>",
                    "location": "San Francisco",
                },
            ],
        },
        {
            "name": "AICompany",
            "location": "New York",
            "jobs": [
                {
                    "id": 22222,
                    "title": "Analytics Engineer",
                    "description": "<p>dbt analytics engineer role.</p>",
                    "location": "Remote",
                }
            ],
        },
    ]
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_relevant_jobs():
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(200, json=_FIXTURE))
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    # Only data engineer + analytics engineer — not PM
    assert len(result.jobs) == 2


@pytest.mark.asyncio
@respx.mock
async def test_parsed_job_fields():
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(200, json=_FIXTURE))
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "12345"
    assert job.title == "Data Engineer"
    assert job.company == "DataStartup"
    assert "workatastartup.com/jobs/12345" in job.apply_url
    assert job.remote is True


@pytest.mark.asyncio
@respx.mock
async def test_empty_body_returns_no_jobs():
    """Empty response body should not raise — return empty result."""
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(200, text=""))
    result = await ADAPTER.fetch()
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_invalid_json_returns_no_jobs():
    """Non-JSON body (e.g. HTML error page) should not raise."""
    respx.get(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, text="<html>Service Unavailable</html>")
    )
    result = await ADAPTER.fetch()
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_304_not_modified():
    respx.get(ADAPTER.source_url).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"etag123"')
    assert result.not_modified is True
    assert result.jobs == []
