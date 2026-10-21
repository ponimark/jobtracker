"""WeWorkRemotely RSS adapter."""
from urllib.parse import urlparse

import feedparser  # type: ignore[import-untyped]

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_FEEDS = {
    "programming": "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "data-science": "https://weworkremotely.com/categories/remote-data-science-jobs.rss",
    "devops": "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
}

_DATA_KEYWORDS = ["data", "engineer", "analytics", "sql", "python", "pipeline", "platform"]


class WWRAdapter(SourceAdapter):
    ats = "weworkremotely"

    @property
    def source_url(self) -> str:
        return _FEEDS.get(self.slug, _FEEDS["programming"])

    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        url = self.source_url
        host = urlparse(url).netloc
        client = get_client(host)
        limiter = get_limiter(host)

        headers: dict[str, str] = {}
        if last_etag:
            headers["If-None-Match"] = last_etag

        async with limiter:
            response = await client.get(url, headers=headers)

        if response.status_code == 304:
            return FetchResult(jobs=[], status_code=304, not_modified=True)

        # Only raise for 4xx/5xx — 3xx redirect bodies are passed to feedparser
        if response.status_code >= 400:
            response.raise_for_status()

        feed = feedparser.parse(response.text)
        jobs = [self._parse_entry(e) for e in feed.entries if self._is_relevant(e)]

        return FetchResult(
            jobs=jobs,
            status_code=response.status_code,
            etag=response.headers.get("etag"),
        )

    def _is_relevant(self, entry: feedparser.FeedParserDict) -> bool:  # type: ignore[name-defined]
        title = (entry.get("title") or "").lower()
        return any(kw in title for kw in _DATA_KEYWORDS)

    def _parse_entry(self, entry: feedparser.FeedParserDict) -> NormalizedJob:  # type: ignore[name-defined]
        desc_html = entry.get("summary", "") or ""
        desc_text = html_to_text(desc_html)
        title = entry.get("title", "")
        # WWR title format: "Company: Job Title"
        parts = title.split(": ", 1)
        company = parts[0].strip() if len(parts) == 2 else self.company_name
        job_title = parts[1].strip() if len(parts) == 2 else title

        return NormalizedJob(
            external_id=entry.get("id", entry.get("link", title)),
            title=job_title,
            company=company,
            apply_url=entry.get("link", ""),
            description_html=desc_html,
            description_text=desc_text,
            location="Remote",
            remote=True,
            seniority=infer_seniority(job_title),
            raw_payload=dict(entry),
        )
