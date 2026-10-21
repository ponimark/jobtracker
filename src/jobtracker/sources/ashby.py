"""Ashby ATS adapter — public posting API."""
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.salary import parse_salary
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter


class AshbyAdapter(SourceAdapter):
    ats = "ashby"

    @property
    def source_url(self) -> str:
        return (
            f"https://api.ashbyhq.com/posting-api/job-board/{self.slug}"
            "?includeCompensation=true"
        )

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
        if last_modified:
            headers["If-Modified-Since"] = last_modified

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
            last_modified=response.headers.get("last-modified"),
        )

    def _parse_job(self, raw: dict) -> NormalizedJob:
        location_text = raw.get("location")
        desc_html = raw.get("descriptionHtml", "") or raw.get("description", "") or ""
        desc_text = html_to_text(desc_html)

        # Ashby sometimes provides compensation directly
        comp = raw.get("compensation") or {}
        sal_min = comp.get("minValue") or comp.get("min")
        sal_max = comp.get("maxValue") or comp.get("max")
        currency = comp.get("currency", "USD")

        if not sal_min and not sal_max:
            parsed = parse_salary(desc_text[:500])
            sal_min, sal_max, currency = parsed.min, parsed.max, parsed.currency

        return NormalizedJob(
            external_id=raw["id"],
            title=raw["title"],
            company=self.company_name,
            apply_url=raw.get("jobUrl", raw.get("applyUrl", "")),
            description_html=desc_html,
            description_text=desc_text,
            location=normalise_location(location_text),
            remote=is_remote(location_text, desc_text),
            employment_type=raw.get("employmentType"),
            seniority=infer_seniority(raw["title"]),
            salary_min=int(sal_min) if sal_min else None,
            salary_max=int(sal_max) if sal_max else None,
            salary_currency=currency,
            raw_payload=raw,
        )
