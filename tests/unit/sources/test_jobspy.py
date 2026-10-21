"""JobSpy adapter unit tests (mocked scrape)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from jobtracker.sources.jobspy import JobSpyAdapter, _row_to_job


SAMPLE_ROWS = [
    {
        "id": "in-4ccac0d43133ffb8",
        "site": "indeed",
        "job_url": "https://www.indeed.com/viewjob?jk=4ccac0d43133ffb8",
        "job_url_direct": "https://www.tesla.com/careers/search/job/278976?source=Indeed",
        "title": "Internship, Data Engineer, Cell Engineering (Fall 2026)",
        "company": "Tesla",
        "location": "Fremont, CA, US",
        "date_posted": "2026-08-05",
        "job_type": "internship",
        "is_remote": False,
        "description": "Data engineer internship at Tesla. SQL and Python.",
        "min_amount": 20.0,
        "max_amount": 50.0,
        "currency": "USD",
    },
    {
        "id": "in-abc",
        "site": "indeed",
        "job_url": "https://www.indeed.com/viewjob?jk=abc",
        "title": "Data Engineer",
        "company": "Acme",
        "location": "Remote",
        "date_posted": "2026-08-01",
        "is_remote": True,
        "description": "Pipelines",
    },
]


@pytest.mark.asyncio
async def test_fetch_maps_tesla_from_indeed():
    adapter = JobSpyAdapter(
        slug="jobspy-tesla-data-engineer-intern",
        search_term="Tesla Data Engineer Intern",
        sites=["indeed", "google"],
    )
    with patch.object(adapter, "_scrape_sync", return_value=SAMPLE_ROWS):
        result = await adapter.fetch()

    assert result.status_code == 200
    assert len(result.jobs) == 2
    tesla = result.jobs[0]
    assert tesla.company == "Tesla"
    assert tesla.external_id == "in-4ccac0d43133ffb8"
    assert "tesla.com/careers" in tesla.apply_url
    assert tesla.seniority == "intern"
    assert tesla.salary_min == 20


def test_row_to_job_skips_empty_title():
    assert _row_to_job({"company": "X", "title": ""}) is None


def test_row_to_job_falls_back_external_id():
    job = _row_to_job(
        {
            "title": "Data Engineer",
            "company": "Foo",
            "job_url": "https://example.com/jobs/1",
            "site": "google",
        }
    )
    assert job is not None
    assert job.external_id.startswith("google-")
