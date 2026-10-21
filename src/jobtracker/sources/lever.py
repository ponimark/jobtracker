"""Lever ATS adapter — public JSON API."""
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.salary import parse_salary
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter


class LeverAdapter(SourceAdapter):
    ats = "lever"

    @property
    def source_url(self) -> str:
        return f"https://api.lever.co/v0/postings/{self.slug}?mode=json"

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

        jobs = [self._parse_job(j) for j in (data if isinstance(data, list) else [])]

        return FetchResult(
            jobs=jobs,
            status_code=response.status_code,
            etag=response.headers.get("etag"),
            last_modified=response.headers.get("last-modified"),
        )

    def _parse_job(self, raw: dict) -> NormalizedJob:
        location_text = raw.get("categories", {}).get("location")
        # Lever description is split into lists — join them
        lists = raw.get("lists", [])
        desc_html = " ".join(
            f"<h3>{lst.get('text', '')}</h3>{lst.get('content', '')}" for lst in lists
        )
        additional = raw.get("additionalPlain", "") or raw.get("descriptionPlain", "") or ""
        desc_text = html_to_text(desc_html) + "\n" + additional

        salary = parse_salary(desc_text[:500])

        return NormalizedJob(
            external_id=raw["id"],
            title=raw["text"],
            company=self.company_name,
            apply_url=raw.get("hostedUrl", raw.get("applyUrl", "")),
            description_html=desc_html,
            description_text=desc_text.strip(),
            location=normalise_location(location_text),
            remote=is_remote(location_text, desc_text),
            employment_type=raw.get("categories", {}).get("commitment"),
            seniority=infer_seniority(raw["text"]),
            salary_min=salary.min,
            salary_max=salary.max,
            salary_currency=salary.currency,
            raw_payload=raw,
        )
