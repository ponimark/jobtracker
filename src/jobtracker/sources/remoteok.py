"""RemoteOK JSON API adapter."""
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_URL = "https://remoteok.com/api"
_DATA_KEYWORDS = ["data", "engineer", "analytics", "sql", "python", "pipeline"]


class RemoteOKAdapter(SourceAdapter):
    ats = "remoteok"

    @property
    def source_url(self) -> str:
        return _URL

    @retry_policy
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

        response.raise_for_status()
        data = response.json()

        # First element is metadata, skip it
        raw_jobs = [j for j in data[1:] if isinstance(j, dict)]
        jobs = [self._parse_job(j) for j in raw_jobs if self._is_relevant(j)]

        return FetchResult(
            jobs=jobs,
            status_code=response.status_code,
            etag=response.headers.get("etag"),
        )

    def _is_relevant(self, raw: dict) -> bool:
        title = (raw.get("position") or "").lower()
        tags = " ".join(raw.get("tags", []) or []).lower()
        text = title + " " + tags
        return any(kw in text for kw in _DATA_KEYWORDS)

    def _parse_job(self, raw: dict) -> NormalizedJob:
        desc_html = raw.get("description", "") or ""
        desc_text = html_to_text(desc_html)

        return NormalizedJob(
            external_id=str(raw["id"]),
            title=raw.get("position", "Unknown"),
            company=raw.get("company", self.company_name),
            apply_url=raw.get("url", f"https://remoteok.com/l/{raw['slug']}"),
            description_html=desc_html,
            description_text=desc_text,
            location="Remote",
            remote=True,
            seniority=infer_seniority(raw.get("position", "")),
            salary_min=raw.get("salary_min"),
            salary_max=raw.get("salary_max"),
            salary_currency="USD",
            raw_payload=raw,
        )
