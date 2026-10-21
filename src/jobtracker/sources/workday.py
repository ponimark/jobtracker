"""Workday ATS adapter — POST-based paginated JSON API."""
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from typing import Any

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.salary import parse_salary
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_PAGE_LIMIT = 20  # Salesforce (and some tenants) 400 on limit > 20
_MAX_JOBS = 500


class WorkdayAdapter(SourceAdapter):
    """Adapter for companies that use Workday ATS.

    Requires extra yaml fields:
      workday_host: company.wd1.myworkdayjobs.com
      workday_path: ExternalCareerSite
    """

    ats = "workday"

    def __init__(self, slug: str, company_name: str | None = None, **kwargs: Any) -> None:
        super().__init__(slug, company_name, **kwargs)
        self._host: str = kwargs.get("workday_host", "")
        self._site: str = kwargs.get("workday_path", "")

    @property
    def source_url(self) -> str:
        return f"https://{self._host}/wday/cxs/{self.slug}/{self._site}/jobs"

    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        if not self._host or not self._site:
            return FetchResult(jobs=[], status_code=0)

        all_jobs: list[NormalizedJob] = []
        last_status = 200
        offset = 0
        known_total: int | None = None

        while offset < _MAX_JOBS:
            data, last_status = await self._fetch_page(offset)
            if data is None:
                break

            postings = data.get("jobPostings", [])
            # Some tenants (Salesforce) return total=0 on offset > 0; trust first page only.
            page_total = int(data.get("total") or 0)
            if known_total is None:
                known_total = page_total

            for posting in postings:
                all_jobs.append(self._parse_posting(posting))

            if not postings:
                break
            offset += len(postings)
            if known_total and offset >= known_total:
                break
            if len(postings) < _PAGE_LIMIT:
                break

        return FetchResult(jobs=all_jobs, status_code=last_status)

    async def _fetch_page(self, offset: int) -> tuple[dict | None, int]:
        url = self.source_url
        host = urlparse(url).netloc
        client = get_client(host)
        limiter = get_limiter(host)

        body = {
            "appliedFacets": {},
            "limit": _PAGE_LIMIT,
            "offset": offset,
            "searchText": "",
        }

        async with limiter:
            response = await client.post(
                url,
                json=body,
                headers={"Content-Type": "application/json"},
            )

        if response.status_code >= 400:
            response.raise_for_status()

        try:
            return response.json(), response.status_code
        except Exception:
            return None, response.status_code

    def _parse_posting(self, raw: dict) -> NormalizedJob:
        external_path = raw.get("externalPath", "")
        base = f"https://{self._host}"
        if external_path.startswith("/"):
            apply_url = f"{base}{external_path}"
        else:
            apply_url = f"{base}/{external_path}"

        location_text = raw.get("locationsText") or raw.get("locationText")
        title = raw.get("title", "")
        job_req_id = (
            raw.get("jobReqId")
            or (raw.get("bulletFields") or [None])[0]
            or external_path
        )
        desc_html = raw.get("description", "") or ""
        desc_text = html_to_text(desc_html) if desc_html else ""
        salary = parse_salary((desc_text or title)[:500])

        return NormalizedJob(
            external_id=str(job_req_id),
            title=title,
            company=self.company_name,
            apply_url=apply_url,
            description_html=desc_html,
            description_text=desc_text,
            location=normalise_location(location_text),
            remote=is_remote(location_text or "", desc_text),
            seniority=infer_seniority(title),
            salary_min=salary.min,
            salary_max=salary.max,
            salary_currency=salary.currency,
            posted_at=_parse_posted_on(raw.get("postedOn", "")),
            raw_payload=raw,
        )


def _parse_posted_on(posted_on: str) -> datetime | None:
    """Convert 'Posted X Days Ago' to a UTC datetime (no tzinfo stored)."""
    if not posted_on:
        return None
    text = posted_on.lower()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if "today" in text or "hour" in text:
        return now
    m = re.search(r"(\d+)\s+day", text)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None
