"""Workable adapter — widget API."""
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter


class WorkableAdapter(SourceAdapter):
    ats = "workable"

    @property
    def source_url(self) -> str:
        return f"https://apply.workable.com/api/v1/widget/accounts/{self.slug}"

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
        jobs = [self._parse_job(j) for j in data.get("jobs", [])]

        return FetchResult(
            jobs=jobs,
            status_code=response.status_code,
            etag=response.headers.get("etag"),
        )

    def _parse_job(self, raw: dict) -> NormalizedJob:
        location_text = raw.get("location", {}).get("location_str")
        desc_html = raw.get("description", "") or ""
        desc_text = html_to_text(desc_html)

        return NormalizedJob(
            external_id=raw["shortcode"],
            title=raw["title"],
            company=self.company_name,
            apply_url=f"https://apply.workable.com/{self.slug}/j/{raw['shortcode']}/",
            description_html=desc_html,
            description_text=desc_text,
            location=normalise_location(location_text),
            remote=is_remote(location_text, desc_text),
            employment_type=raw.get("employment_type"),
            seniority=infer_seniority(raw["title"]),
            raw_payload=raw,
        )
