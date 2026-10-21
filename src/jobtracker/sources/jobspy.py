"""JobSpy multi-board search adapter (Indeed / Google).

Wraps ``python-jobspy`` so we pick up postings that ATS boards miss, such as roles that Indeed indexes from
company career pages.

sources.yaml example::

    - ats: jobspy
      slug: jobspy-tesla-de-intern
      name: JobSpy — Tesla DE intern
      search_term: Tesla Data Engineer Intern
      location: United States
      sites: [indeed, google]
      results_wanted: 25
      hours_old: 168
      poll_interval_s: 21600
"""
from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from typing import Any

from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_DEFAULT_SITES = ["indeed", "google"]


class JobSpyAdapter(SourceAdapter):
    ats = "jobspy"

    def __init__(
        self,
        slug: str,
        company_name: str | None = None,
        search_term: str | None = None,
        keywords: str | None = None,
        query: str | None = None,
        location: str = "United States",
        sites: list[str] | None = None,
        results_wanted: int = 25,
        hours_old: int = 168,
        country_indeed: str = "USA",
        google_search_term: str | None = None,
        is_remote: bool = False,
        **kwargs: object,
    ) -> None:
        super().__init__(slug=slug, company_name=company_name, **kwargs)
        raw = search_term or keywords or query or slug.replace("-", " ")
        self.search_term = str(raw).strip()
        self.location = (location or "").strip()
        self.sites = [str(s).strip().lower() for s in (sites or _DEFAULT_SITES) if s and str(s).strip().lower() != "linkedin"]
        self.results_wanted = max(1, int(results_wanted))
        self.hours_old = max(1, int(hours_old))
        self.country_indeed = country_indeed or "USA"
        self.google_search_term = (google_search_term or "").strip() or None
        self.is_remote = bool(is_remote)

    @property
    def source_url(self) -> str:
        return f"jobspy://{','.join(self.sites)}/{self.search_term}"

    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        rows = await asyncio.to_thread(self._scrape_sync)
        jobs = [j for j in (_row_to_job(r) for r in rows) if j is not None]
        return FetchResult(jobs=jobs, status_code=200)

    def _scrape_sync(self) -> list[dict[str, Any]]:
        try:
            from jobspy import scrape_jobs
        except ImportError as exc:
            raise RuntimeError(
                "python-jobspy is not installed. "
                "Run: pip install 'python-jobspy>=1.1.82'"
            ) from exc

        kwargs: dict[str, Any] = {
            "site_name": self.sites,
            "search_term": self.search_term,
            "location": self.location,
            "results_wanted": self.results_wanted,
            "hours_old": self.hours_old,
            "country_indeed": self.country_indeed,
            "verbose": 0,
        }
        if self.is_remote:
            kwargs["is_remote"] = True
        if self.google_search_term:
            kwargs["google_search_term"] = self.google_search_term
        elif self.location:
            kwargs["google_search_term"] = (
                f"{self.search_term} jobs near {self.location} since last week"
            )

        df = scrape_jobs(**kwargs)
        if df is None or getattr(df, "empty", True):
            return []
        records = df.where(df.notna(), None).to_dict(orient="records")
        return [_clean_record(r) for r in records]


def _clean_record(record: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for key, value in record.items():
        if hasattr(value, "item"):
            try:
                value = value.item()
            except Exception:
                value = str(value)
        if hasattr(value, "isoformat"):
            value = value.isoformat()
        clean[str(key)] = value
    return clean


def _row_to_job(raw: dict[str, Any]) -> NormalizedJob | None:
    title = str(raw.get("title") or "").strip()
    company = str(raw.get("company") or "").strip()
    if not title:
        return None

    apply_url = str(
        raw.get("job_url_direct") or raw.get("job_url") or raw.get("url") or ""
    ).strip()
    external_id = _external_id(raw, apply_url, company, title)
    desc = str(raw.get("description") or "")
    # JobSpy markdown escapes (large\-scale, C\+\+) — normalize before skill extract.
    desc = (
        desc.replace("\\-", "-")
        .replace("\\+", "+")
        .replace("\\*", "*")
        .replace("\\_", "_")
    )
    location_str = str(raw.get("location") or "")
    salary_min = _to_int(raw.get("min_amount"))
    salary_max = _to_int(raw.get("max_amount"))
    # JobSpy amounts are often hourly for internships; keep as-is (same as Adzuna).
    remote_flag = raw.get("is_remote")
    if isinstance(remote_flag, bool):
        remote = remote_flag
    else:
        remote = is_remote(location_str, desc)

    job_type = raw.get("job_type")
    employment_type = str(job_type) if job_type else None

    return NormalizedJob(
        external_id=external_id,
        title=title,
        company=company or "Unknown",
        apply_url=apply_url,
        description_html="",
        description_text=html_to_text(desc) if desc else "",
        location=normalise_location(location_str) if location_str else None,
        remote=remote,
        employment_type=employment_type,
        seniority=infer_seniority(title),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=str(raw.get("currency") or "USD"),
        posted_at=_parse_date(raw.get("date_posted")),
        raw_payload=raw,
    )


def _external_id(raw: dict[str, Any], apply_url: str, company: str, title: str) -> str:
    job_id = raw.get("id")
    if job_id:
        return str(job_id)
    site = str(raw.get("site") or "jobspy")
    if apply_url:
        digest = hashlib.sha1(apply_url.encode("utf-8")).hexdigest()[:16]
        return f"{site}-{digest}"
    digest = hashlib.sha1(f"{company}|{title}".encode("utf-8")).hexdigest()[:16]
    return f"{site}-{digest}"


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_date(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 10:
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None
