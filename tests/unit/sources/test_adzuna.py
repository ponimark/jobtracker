import httpx
import pytest
import respx

from jobtracker.config import settings
from jobtracker.sources.adzuna import AdzunaAdapter


@pytest.fixture(autouse=True)
def _adzuna_creds(monkeypatch):
    monkeypatch.setattr(settings, "adzuna_app_id", "test_app_id")
    monkeypatch.setattr(settings, "adzuna_app_key", "test_app_key")


ADAPTER = AdzunaAdapter(
    slug="data-engineer-us-remote",
    company_name="Adzuna US",
    query="data engineer",
    location="remote",
    country="us",
    max_days_old=7,
)

_URL = "https://api.adzuna.com/v1/api/jobs/us/search/1"

_SAMPLE_RESPONSE = {
    "count": 2,
    "results": [
        {
            "id": "4238273192",
            "title": "Data Engineer",
            "company": {"display_name": "Acme Analytics"},
            "location": {"display_name": "Remote, US", "area": ["US"]},
            "description": "Build pipelines with dbt and Snowflake.",
            "redirect_url": "https://www.adzuna.com/land/ad/4238273192",
            "created": "2026-04-17T14:22:11Z",
            "salary_min": 95000,
            "salary_max": 140000,
            "contract_type": "permanent",
        },
        {
            "id": "4238273193",
            "title": "Senior Analytics Engineer",
            "company": {"display_name": "BigCo"},
            "location": {"display_name": "San Francisco, CA"},
            "description": "dbt and Snowflake.",
            "redirect_url": "https://www.adzuna.com/land/ad/4238273193",
            "created": "2026-04-16T09:00:00Z",
            "salary_min": None,
            "salary_max": None,
        },
    ],
}


@pytest.mark.asyncio
@respx.mock
async def test_fetch_parses_results():
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_SAMPLE_RESPONSE))
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    assert len(result.jobs) == 2


@pytest.mark.asyncio
@respx.mock
async def test_fields_mapped_correctly():
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_SAMPLE_RESPONSE))
    result = await ADAPTER.fetch()
    job = result.jobs[0]
    assert job.external_id == "4238273192"
    assert job.title == "Data Engineer"
    assert job.company == "Acme Analytics"
    assert job.apply_url == "https://www.adzuna.com/land/ad/4238273192"
    assert job.salary_min == 95000
    assert job.salary_max == 140000
    assert job.salary_currency == "USD"
    assert job.remote is True
    assert job.employment_type == "permanent"


@pytest.mark.asyncio
@respx.mock
async def test_non_remote_job_not_flagged_remote():
    respx.get(_URL).mock(return_value=httpx.Response(200, json=_SAMPLE_RESPONSE))
    result = await ADAPTER.fetch()
    sf_job = result.jobs[1]
    assert sf_job.remote is not True
    assert sf_job.location and "San Francisco" in sf_job.location


@pytest.mark.asyncio
@respx.mock
async def test_missing_credentials_raises():
    adapter = AdzunaAdapter(slug="x", query="data engineer")
    import jobtracker.sources.adzuna as mod
    original_id = mod.settings.adzuna_app_id
    original_key = mod.settings.adzuna_app_key
    mod.settings.adzuna_app_id = ""
    mod.settings.adzuna_app_key = ""
    try:
        with pytest.raises(RuntimeError, match="Adzuna credentials"):
            await adapter.fetch()
    finally:
        mod.settings.adzuna_app_id = original_id
        mod.settings.adzuna_app_key = original_key


@pytest.mark.asyncio
@respx.mock
async def test_uk_country_uses_gbp():
    adapter = AdzunaAdapter(slug="x", query="data engineer", country="gb")
    respx.get("https://api.adzuna.com/v1/api/jobs/gb/search/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "1",
                        "title": "Data Engineer",
                        "company": {"display_name": "UKCorp"},
                        "location": {"display_name": "London"},
                        "description": "",
                        "redirect_url": "https://adzuna.co.uk/1",
                        "created": "2026-04-17T00:00:00Z",
                        "salary_min": 60000,
                        "salary_max": 80000,
                    }
                ]
            },
        )
    )
    result = await adapter.fetch()
    assert result.jobs[0].salary_currency == "GBP"


@pytest.mark.asyncio
@respx.mock
async def test_empty_results_no_crash():
    respx.get(_URL).mock(return_value=httpx.Response(200, json={"results": []}))
    result = await ADAPTER.fetch()
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_salary_overflow_filtered():
    payload = {
        "results": [
            {
                "id": "1",
                "title": "Data Engineer",
                "company": {"display_name": "X"},
                "location": {"display_name": "Remote"},
                "description": "",
                "redirect_url": "https://x/1",
                "created": "2026-04-17T00:00:00Z",
                "salary_min": 99999999999,
                "salary_max": 99999999999,
            }
        ]
    }
    respx.get(_URL).mock(return_value=httpx.Response(200, json=payload))
    result = await ADAPTER.fetch()
    job = result.jobs[0]
    assert job.salary_min is None
    assert job.salary_max is None
