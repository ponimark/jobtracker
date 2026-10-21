"""Company careers-site adapter for big employers with public JSON search APIs.

One adapter, one site per yaml entry. Required yaml field:
  site: amazon | microsoft | jpmorgan
Optional:
  queries: [list of search keywords]  (default: data engineer)
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_AMAZON = "https://www.amazon.jobs"
_MSFT = "https://apply.careers.microsoft.com"
_JPM = "https://jpmc.fa.oraclecloud.com"
_PAGE = 50
_MAX_PER_QUERY = 200


class CareersAdapter(SourceAdapter):
    ats = "careers"
    supports_two_phase = True

    def __init__(self, slug: str, company_name: str | None = None, **kwargs: Any) -> None:
        super().__init__(slug, company_name, **kwargs)
        self._site: str = kwargs.get("site", slug)
        self._queries: list[str] = kwargs.get("queries") or ["data engineer"]

    @property
    def source_url(self) -> str:
        return {"amazon": _AMAZON, "microsoft": _MSFT, "jpmorgan": _JPM}.get(self._site, "")

    async def fetch(self, last_etag=None, last_modified=None) -> FetchResult:
        return await self.fetch_list(last_etag, last_modified)

    async def fetch_list(self, last_etag=None, last_modified=None) -> FetchResult:
        fn = {"amazon": self._amazon, "microsoft": self._microsoft, "jpmorgan": self._jpmorgan}.get(self._site)
        if fn is None:
            return FetchResult(jobs=[], status_code=0)
        seen: dict[str, NormalizedJob] = {}
        status = 200
        for q in self._queries:
            jobs, status = await fn(q)
            for j in jobs:
                seen.setdefault(j.external_id, j)
        return FetchResult(jobs=list(seen.values()), status_code=status)

    async def fetch_details_for(self, jobs: list[NormalizedJob]) -> None:
        if self._site != "microsoft":
            return
        client = get_client("apply.careers.microsoft.com")
        limiter = get_limiter("apply.careers.microsoft.com")

        async def one(job: NormalizedJob) -> None:
            pid = job.raw_payload.get("id")
            try:
                async with limiter:
                    r = await client.get(
                        f"{_MSFT}/api/pcsx/position_details"
                        f"?position_id={pid}&domain=microsoft.com&hl=en"
                    )
                html = (r.json().get("data") or {}).get("jobDescription") or ""
            except Exception:
                return
            job.description_html = html
            job.description_text = html_to_text(html) if html else ""

        await asyncio.gather(*(one(j) for j in jobs))

    async def _get(self, host: str, url: str) -> tuple[dict | None, int]:
        client = get_client(host)
        limiter = get_limiter(host)
        async with limiter:
            r = await client.get(url)
        if r.status_code >= 400:
            r.raise_for_status()
        try:
            return r.json(), r.status_code
        except Exception:
            return None, r.status_code

    # ── Amazon ────────────────────────────────────────────────────────────
    async def _amazon(self, query: str) -> tuple[list[NormalizedJob], int]:
        out: list[NormalizedJob] = []
        status = 200
        offset = 0
        while offset < _MAX_PER_QUERY:
            url = (
                f"{_AMAZON}/en/search.json?base_query={quote(query)}"
                f"&result_limit={_PAGE}&offset={offset}&sort=recent&country%5B%5D=USA"
            )
            data, status = await self._get("www.amazon.jobs", url)
            jobs = (data or {}).get("jobs") or []
            for r in jobs:
                desc = "<br/>".join(
                    x for x in (r.get("description"), r.get("basic_qualifications"),
                                r.get("preferred_qualifications")) if x
                )
                loc = r.get("normalized_location") or r.get("location")
                out.append(NormalizedJob(
                    external_id=str(r.get("id_icims") or r.get("id")),
                    title=r.get("title", ""),
                    company=self.company_name,
                    apply_url=f"{_AMAZON}{r.get('job_path', '')}",
                    description_html=desc,
                    description_text=html_to_text(desc),
                    location=normalise_location(loc),
                    remote=is_remote(loc or "", desc),
                    seniority=infer_seniority(r.get("title", "")),
                    posted_at=_parse_amazon_date(r.get("posted_date")),
                    raw_payload={"id": r.get("id_icims"), "job_family": r.get("job_family")},
                ))
            if len(jobs) < _PAGE:
                break
            offset += _PAGE
        return out, status

    # ── Microsoft ─────────────────────────────────────────────────────────
    async def _microsoft(self, query: str) -> tuple[list[NormalizedJob], int]:
        out: list[NormalizedJob] = []
        status = 200
        start = 0
        while start < _MAX_PER_QUERY:
            url = (
                f"{_MSFT}/api/pcsx/search?domain=microsoft.com&query={quote(query)}"
                f"&location={quote('United States')}&start={start}&num={_PAGE}"
            )
            data, status = await self._get("apply.careers.microsoft.com", url)
            positions = ((data or {}).get("data") or {}).get("positions") or []
            for r in positions:
                locs = r.get("standardizedLocations") or r.get("locations") or []
                loc = locs[0] if locs else None
                posted = r.get("postedTs")
                out.append(NormalizedJob(
                    external_id=str(r.get("displayJobId") or r.get("id")),
                    title=r.get("name", ""),
                    company=self.company_name,
                    apply_url=f"{_MSFT}{r.get('positionUrl', '')}",
                    location=normalise_location(loc),
                    remote=is_remote(loc or "", ""),
                    seniority=infer_seniority(r.get("name", "")),
                    posted_at=datetime.fromtimestamp(posted, tz=timezone.utc).replace(tzinfo=None) if posted else None,
                    raw_payload={"id": r.get("id"), "department": r.get("department")},
                ))
            if len(positions) < _PAGE:
                break
            start += _PAGE
        return out, status

    # ── JPMorgan (Oracle HCM) ─────────────────────────────────────────────
    async def _jpmorgan(self, query: str) -> tuple[list[NormalizedJob], int]:
        out: list[NormalizedJob] = []
        status = 200
        offset = 0
        while offset < _MAX_PER_QUERY:
            finder = (
                f"findReqs;siteNumber=CX_1001,keyword=%22{quote(query)}%22,"
                f"limit={_PAGE},offset={offset},sortBy=POSTING_DATES_DESC,"
                f"locationId=300000000289738"  # United States
            )
            url = (
                f"{_JPM}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
                f"?onlyData=true&expand=requisitionList&finder={finder}"
            )
            data, status = await self._get("jpmc.fa.oraclecloud.com", url)
            items = (data or {}).get("items") or []
            reqs = (items[0].get("requisitionList") if items else None) or []
            for r in reqs:
                title = r.get("Title", "")
                desc = r.get("ShortDescriptionStr") or ""
                loc = r.get("PrimaryLocation")
                rid = str(r.get("Id"))
                out.append(NormalizedJob(
                    external_id=rid,
                    title=title,
                    company=self.company_name,
                    apply_url=f"{_JPM}/hcmUI/CandidateExperience/en/sites/CX_1001/job/{rid}",
                    description_html=desc,
                    description_text=html_to_text(desc) if desc else "",
                    location=normalise_location(loc),
                    remote=is_remote(loc or "", desc),
                    seniority=infer_seniority(title),
                    posted_at=_parse_iso(r.get("PostedDate")),
                    raw_payload={"job_family": r.get("JobFamily")},
                ))
            if len(reqs) < _PAGE:
                break
            offset += _PAGE
        return out, status


def _parse_amazon_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.strptime(" ".join(s.split()), "%B %d, %Y")
    except ValueError:
        return None


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None
