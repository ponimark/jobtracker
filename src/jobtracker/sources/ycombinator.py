"""YC Work at a Startup adapter."""
from urllib.parse import urlparse

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_BASE = "https://www.workatastartup.com"
_DATA_KEYWORDS = {"data engineer", "data engineering", "analytics engineer", "data platform"}


class YCombinatorAdapter(SourceAdapter):
    ats = "ycombinator"

    @property
    def source_url(self) -> str:
        return f"{_BASE}/companies.json?demographic=any&hasEquity=any&hasSalary=any&industry=B2B+Software+and+Services&industry=Data+Engineering&jobType=fulltime&remote=any&roles=eng&sortBy=created"

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
        body = response.text.strip()
        if not body:
            return FetchResult(jobs=[], status_code=response.status_code)
        try:
            data = response.json()
        except Exception:
            return FetchResult(jobs=[], status_code=response.status_code)

        jobs: list[NormalizedJob] = []
        for company in data.get("companies", []):
            for job in company.get("jobs", []):
                if self._is_relevant(job):
                    jobs.append(self._parse_job(job, company))

        return FetchResult(
            jobs=jobs,
            status_code=response.status_code,
            etag=response.headers.get("etag"),
        )

    def _is_relevant(self, job: dict) -> bool:
        title = (job.get("title") or "").lower()
        return any(kw in title for kw in _DATA_KEYWORDS)

    def _parse_job(self, job: dict, company: dict) -> NormalizedJob:
        desc_html = job.get("description", "") or ""
        desc_text = html_to_text(desc_html)
        location_text = job.get("location") or company.get("location")

        return NormalizedJob(
            external_id=str(job["id"]),
            title=job["title"],
            company=company.get("name", self.company_name),
            apply_url=f"{_BASE}/jobs/{job['id']}",
            description_html=desc_html,
            description_text=desc_text,
            location=normalise_location(location_text),
            remote=is_remote(location_text, desc_text),
            seniority=infer_seniority(job["title"]),
            raw_payload={"job": job, "company": company},
        )
