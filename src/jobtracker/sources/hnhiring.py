"""HN 'Who is Hiring' adapter via Algolia search API.

Fetches the most recent 'Ask HN: Who is Hiring?' story, then pulls
all comments that mention data engineering roles.
"""
import re
from datetime import datetime
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
_HN_BASE = "https://news.ycombinator.com"

_KEYWORDS = [
    "data engineer",
    "data engineering",
    "analytics engineer",
    "data platform",
    "data infrastructure",
    "data pipeline",
]


class HNHiringAdapter(SourceAdapter):
    """Scrapes the monthly 'Ask HN: Who is Hiring?' thread for data engineering roles."""

    ats = "hnhiring"

    @property
    def source_url(self) -> str:
        return f"{_ALGOLIA_BASE}/search?query=Ask+HN+Who+is+hiring&tags=story&hitsPerPage=3"

    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        host = urlparse(_ALGOLIA_BASE).netloc
        client = get_client(host)
        limiter = get_limiter(host)

        # Step 1: find the most recent "Who is Hiring" story
        async with limiter:
            resp = await client.get(
                f"{_ALGOLIA_BASE}/search",
                params={
                    "query": "Ask HN: Who is hiring",
                    "tags": "story",
                    "hitsPerPage": "3",
                },
            )
        resp.raise_for_status()

        try:
            stories = resp.json().get("hits", [])
        except Exception:
            return FetchResult(jobs=[], status_code=resp.status_code)

        if not stories:
            return FetchResult(jobs=[], status_code=resp.status_code)

        story_id = stories[0]["objectID"]

        # Step 2: fetch comments from that story matching "data engineer"
        async with limiter:
            resp2 = await client.get(
                f"{_ALGOLIA_BASE}/search",
                params={
                    "tags": f"comment,story_{story_id}",
                    "query": "data engineer",
                    "hitsPerPage": "1000",
                },
            )
        resp2.raise_for_status()

        try:
            hits = resp2.json().get("hits", [])
        except Exception:
            return FetchResult(jobs=[], status_code=resp2.status_code)

        jobs = [self._parse_hit(hit) for hit in hits if self._is_relevant(hit)]

        return FetchResult(jobs=jobs, status_code=resp2.status_code)

    def _is_relevant(self, hit: dict) -> bool:
        text = (hit.get("comment_text") or "").lower()
        return any(kw in text for kw in _KEYWORDS)

    def _parse_hit(self, hit: dict) -> NormalizedJob:
        raw_html = hit.get("comment_text") or ""
        text = html_to_text(raw_html)
        first_line = text.split("\n")[0].strip() if text else ""

        # HN postings often follow: "Company | Role | Location | Remote | Salary"
        parts = [p.strip() for p in re.split(r"\s*\|\s*", first_line)]
        company = parts[0] if parts else self.company_name
        title = parts[1] if len(parts) > 1 else "Data Engineer"
        location_hint = " ".join(parts[2:]) if len(parts) > 2 else ""

        apply_url = f"{_HN_BASE}/item?id={hit['objectID']}"
        posted_at = _parse_created_at(hit.get("created_at"))

        return NormalizedJob(
            external_id=str(hit["objectID"]),
            title=title,
            company=company,
            apply_url=apply_url,
            description_html=raw_html,
            description_text=text,
            location=normalise_location(location_hint) if location_hint else None,
            remote=is_remote(location_hint, text),
            seniority=infer_seniority(title),
            posted_at=posted_at,
            raw_payload=hit,
        )


def _parse_created_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None
