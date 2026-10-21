import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.workday import WorkdayAdapter, _parse_posted_on
from datetime import datetime, timedelta

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "workday_netflix.json").read_text()
)

ADAPTER = WorkdayAdapter(
    slug="netflix",
    company_name="Netflix",
    workday_host="netflix.wd1.myworkdayjobs.com",
    workday_path="Netflix_External_Site",
)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_jobs():
    respx.post(ADAPTER.source_url).mock(return_value=httpx.Response(200, json=FIXTURE))
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 2
    assert not result.not_modified


@pytest.mark.asyncio
@respx.mock
async def test_parsed_job_fields():
    respx.post(ADAPTER.source_url).mock(return_value=httpx.Response(200, json=FIXTURE))
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "JR-0000001"
    assert job.title == "Data Engineer"
    assert job.company == "Netflix"
    assert "netflix.wd1.myworkdayjobs.com" in job.apply_url
    assert job.remote is True
    assert job.seniority is None  # "Data Engineer" has no explicit seniority keyword


@pytest.mark.asyncio
@respx.mock
async def test_senior_seniority_parsed():
    respx.post(ADAPTER.source_url).mock(return_value=httpx.Response(200, json=FIXTURE))
    result = await ADAPTER.fetch()
    senior_job = result.jobs[1]
    assert senior_job.seniority == "senior"


@pytest.mark.asyncio
@respx.mock
async def test_salary_parsed_from_description():
    respx.post(ADAPTER.source_url).mock(return_value=httpx.Response(200, json=FIXTURE))
    result = await ADAPTER.fetch()
    senior_job = result.jobs[1]
    assert senior_job.salary_min == 180_000
    assert senior_job.salary_max == 220_000


@pytest.mark.asyncio
@respx.mock
async def test_empty_response_returns_no_jobs():
    respx.post(ADAPTER.source_url).mock(
        return_value=httpx.Response(200, json={"total": 0, "jobPostings": []})
    )
    result = await ADAPTER.fetch()
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_pagination_ignores_zero_total_on_later_pages():
    """Salesforce returns total=0 for offset > 0; must keep paging until empty/short page."""
    page0 = {"total": 45, "jobPostings": [{"title": f"Job {i}", "externalPath": f"/job/{i}", "bulletFields": [str(i)]} for i in range(20)]}
    page1 = {"total": 0, "jobPostings": [{"title": f"Job {i}", "externalPath": f"/job/{i}", "bulletFields": [str(i)]} for i in range(20, 40)]}
    page2 = {"total": 0, "jobPostings": [{"title": f"Job {i}", "externalPath": f"/job/{i}", "bulletFields": [str(i)]} for i in range(40, 45)]}
    respx.post(ADAPTER.source_url).mock(side_effect=[
        httpx.Response(200, json=page0),
        httpx.Response(200, json=page1),
        httpx.Response(200, json=page2),
    ])
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 45


@pytest.mark.asyncio
@respx.mock
async def test_page_limit_is_at_most_20():
    """Workday Salesforce 400s when limit > 20 — body must stay <= 20."""
    captured: list[dict] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content.decode()))
        return httpx.Response(200, json={"total": 1, "jobPostings": []})

    respx.post(ADAPTER.source_url).mock(side_effect=_capture)
    await ADAPTER.fetch()
    assert captured
    assert captured[0]["limit"] <= 20


@pytest.mark.asyncio
async def test_missing_host_returns_empty():
    adapter = WorkdayAdapter(slug="test", company_name="Test")
    result = await adapter.fetch()
    assert result.jobs == []
    assert result.status_code == 0


def test_parse_posted_on_days():
    now = datetime.utcnow()
    result = _parse_posted_on("Posted 5 Days Ago")
    assert result is not None
    delta = now - result
    assert 4 <= delta.days <= 6


def test_parse_posted_on_today():
    now = datetime.utcnow()
    result = _parse_posted_on("Posted Today")
    assert result is not None
    assert (now - result).total_seconds() < 60


def test_parse_posted_on_empty():
    assert _parse_posted_on("") is None
    assert _parse_posted_on(None) is None
