"""SmartRecruiters adapter — public postings API."""
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.salary import parse_salary
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_BASE = "https://api.smartrecruiters.com/v1/companies"


class SmartRecruitersAdapter(SourceAdapter):
    ats = "smartrecruiters"

    @property
    def source_url(self) -> str:
        return f"{_BASE}/{self.slug}/postings"

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

        all_jobs: list[NormalizedJob] = []
        offset = 0
        limit = 100

        while True:
            async with limiter:
                response = await client.get(
                    url,
                    headers=headers,
                    params={"limit": limit, "offset": offset},
                )

            if response.status_code == 304:
                return FetchResult(jobs=[], status_code=304, not_modified=True)

            response.raise_for_status()
            data = response.json()
            items = data.get("content", [])
            all_jobs.extend(self._parse_job(j) for j in items)

            total = data.get("totalFound", 0)
            offset += limit
            if offset >= total or not items:
                break

        return FetchResult(
            jobs=all_jobs,
            status_code=200,
            etag=response.headers.get("etag"),
        )

    def _parse_job(self, raw: dict) -> NormalizedJob:
        loc = raw.get("location", {})
        location_text = ", ".join(
            filter(None, [loc.get("city"), loc.get("region"), loc.get("country")])
        )
        desc_html = raw.get("jobAd", {}).get("sections", {}).get("jobDescription", {}).get(
            "text", ""
        ) or ""
        desc_text = html_to_text(desc_html)
        salary = parse_salary(desc_text[:500])
        remote_flag = loc.get("remote")

        return NormalizedJob(
            external_id=raw["id"],
            title=raw["name"],
            company=self.company_name,
            apply_url=f"https://jobs.smartrecruiters.com/{self.slug}/{raw['id']}",
            description_html=desc_html,
            description_text=desc_text,
            location=normalise_location(location_text) or None,
            remote=remote_flag if isinstance(remote_flag, bool) else is_remote(location_text),
            employment_type=raw.get("typeOfEmployment", {}).get("label"),
            seniority=infer_seniority(raw["name"]),
            salary_min=salary.min,
            salary_max=salary.max,
            salary_currency=salary.currency,
            raw_payload=raw,
        )
