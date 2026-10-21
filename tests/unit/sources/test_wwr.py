import httpx
import pytest
import respx

from jobtracker.sources.wwr import WWRAdapter

ADAPTER = WWRAdapter(slug="data-science", company_name="WeWorkRemotely Data")

_DATA_SCIENCE_URL = "https://weworkremotely.com/categories/remote-data-science-jobs.rss"

_SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>WeWorkRemotely: Remote Data Science Jobs</title>
    <item>
      <title>Acme: Data Engineer</title>
      <link>https://weworkremotely.com/remote-jobs/acme-data-engineer</link>
      <guid>https://weworkremotely.com/remote-jobs/acme-data-engineer</guid>
      <description><![CDATA[<p>We are hiring a data engineer.</p>]]></description>
    </item>
    <item>
      <title>BigCo: Senior SQL Developer</title>
      <link>https://weworkremotely.com/remote-jobs/bigco-sql-developer</link>
      <guid>https://weworkremotely.com/remote-jobs/bigco-sql-developer</guid>
      <description><![CDATA[<p>Senior SQL role.</p>]]></description>
    </item>
    <item>
      <title>StartupX: iOS Developer</title>
      <link>https://weworkremotely.com/remote-jobs/startupx-ios</link>
      <guid>https://weworkremotely.com/remote-jobs/startupx-ios</guid>
      <description><![CDATA[<p>iOS developer role.</p>]]></description>
    </item>
  </channel>
</rss>"""


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_relevant_jobs():
    respx.get(_DATA_SCIENCE_URL).mock(
        return_value=httpx.Response(200, text=_SAMPLE_RSS)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    # iOS Developer should be filtered out — only data/engineer/sql/python jobs kept
    assert len(result.jobs) == 2


@pytest.mark.asyncio
@respx.mock
async def test_fetch_304_not_modified():
    respx.get(_DATA_SCIENCE_URL).mock(return_value=httpx.Response(304))
    result = await ADAPTER.fetch(last_etag='"abc"')
    assert result.not_modified is True
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_html_response_returns_empty_not_error():
    """When URL returns HTML instead of RSS, feedparser returns 0 entries — no exception raised."""
    respx.get(_DATA_SCIENCE_URL).mock(
        return_value=httpx.Response(
            200,
            text="<html><body><h1>Page moved</h1></body></html>",
        )
    )
    result = await ADAPTER.fetch()
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_job_company_parsed_from_title():
    respx.get(_DATA_SCIENCE_URL).mock(
        return_value=httpx.Response(200, text=_SAMPLE_RSS)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]
    assert job.company == "Acme"
    assert job.title == "Data Engineer"


@pytest.mark.asyncio
@respx.mock
async def test_job_is_remote():
    respx.get(_DATA_SCIENCE_URL).mock(
        return_value=httpx.Response(200, text=_SAMPLE_RSS)
    )
    result = await ADAPTER.fetch()
    assert all(job.remote is True for job in result.jobs)
