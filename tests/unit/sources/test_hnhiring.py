import json
from pathlib import Path

import httpx
import pytest
import respx

from jobtracker.sources.hnhiring import HNHiringAdapter, _parse_created_at

STORIES_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "hnhiring_stories.json").read_text()
)
COMMENTS_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "hnhiring_comments.json").read_text()
)

ADAPTER = HNHiringAdapter(slug="whoishiring", company_name="HN Who is Hiring")

_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
_STORY_ID = "99000001"
_SEARCH_URL = f"{_ALGOLIA_BASE}/search"


@pytest.mark.asyncio
@respx.mock
async def test_fetch_returns_relevant_jobs():
    respx.get(_SEARCH_URL, params__contains={"query": "Ask HN: Who is hiring"}).mock(
        return_value=httpx.Response(200, json=STORIES_FIXTURE)
    )
    respx.get(_SEARCH_URL, params__contains={"tags": f"comment,story_{_STORY_ID}"}).mock(
        return_value=httpx.Response(200, json=COMMENTS_FIXTURE)
    )
    result = await ADAPTER.fetch()
    assert result.status_code == 200
    # Should only return the 2 data engineer jobs, not the React job
    assert len(result.jobs) == 2


@pytest.mark.asyncio
@respx.mock
async def test_job_fields_parsed_correctly():
    respx.get(_SEARCH_URL, params__contains={"query": "Ask HN: Who is hiring"}).mock(
        return_value=httpx.Response(200, json=STORIES_FIXTURE)
    )
    respx.get(_SEARCH_URL, params__contains={"tags": f"comment,story_{_STORY_ID}"}).mock(
        return_value=httpx.Response(200, json=COMMENTS_FIXTURE)
    )
    result = await ADAPTER.fetch()
    job = result.jobs[0]

    assert job.external_id == "99100001"
    assert job.company == "Acme Corp"
    assert job.title == "Data Engineer"
    assert "news.ycombinator.com" in job.apply_url
    assert job.remote is True


@pytest.mark.asyncio
@respx.mock
async def test_no_stories_returns_empty():
    respx.get(_SEARCH_URL).mock(
        return_value=httpx.Response(200, json={"hits": []})
    )
    result = await ADAPTER.fetch()
    assert result.jobs == []


@pytest.mark.asyncio
@respx.mock
async def test_invalid_story_json_returns_empty():
    respx.get(_SEARCH_URL).mock(
        return_value=httpx.Response(200, text="not json")
    )
    result = await ADAPTER.fetch()
    assert result.jobs == []


def test_parse_created_at_valid():
    dt = _parse_created_at("2026-04-01T14:00:00Z")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 4


def test_parse_created_at_none():
    assert _parse_created_at(None) is None
    assert _parse_created_at("") is None
