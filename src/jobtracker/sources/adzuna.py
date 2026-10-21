"""Adzuna API adapter.

Docs: https://developer.adzuna.com/docs/search

Endpoint::

    GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
        ?app_id=...&app_key=...&what=...&where=...&results_per_page=50&sort_by=date

Adzuna aggregates listings from Indeed, CareerBuilder, Reed, and many others.
Auth is via ``app_id`` + ``app_key`` query params (set in ``.env``).

sources.yaml example::

    - ats: adzuna
      slug: data-engineer-us-remote
      name: Adzuna (data engineer, US remote)
      query: data engineer          # 'what' param — required
      location: remote              # 'where' param — optional
      country: us                   # us, gb, au, ca, de, fr, ... (default us)
      max_days_old: 7               # optional, filters by created date
"""
from datetime import datetime
from urllib.parse import urlparse

from jobtracker.config import settings
from jobtracker.http.client import get_client
from jobtracker.http.ratelimit import get_limiter
from jobtracker.http.retry import retry_policy
from jobtracker.normalize.html import html_to_text
from jobtracker.normalize.location import is_remote, normalise_location
from jobtracker.normalize.seniority import infer_seniority
from jobtracker.sources.base import FetchResult, NormalizedJob, SourceAdapter

_API_HOST = "https://api.adzuna.com"
_RESULTS_PER_PAGE = 50


class AdzunaAdapter(SourceAdapter):
    ats = "adzuna"

    def __init__(
        self,
        slug: str,
        company_name: str | None = None,
        query: str | None = None,
        location: str = "",
        country: str = "us",
        max_days_old: int | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(slug=slug, company_name=company_name, **kwargs)
        self.query = (query or slug.replace("-", " ")).strip()
        self.location = location.strip()
        self.country = (country or "us").strip().lower()
        self.max_days_old = max_days_old

    @property
    def source_url(self) -> str:
        return f"{_API_HOST}/v1/api/jobs/{self.country}/search/1"

    def _params(self) -> dict[str, str]:
        params: dict[str, str] = {
            "app_id": settings.adzuna_app_id,
            "app_key": settings.adzuna_app_key,
            "what": self.query,
            "results_per_page": str(_RESULTS_PER_PAGE),
            "sort_by": "date",
            "content-type": "application/json",
        }
        if self.location:
            params["where"] = self.location
        if self.max_days_old is not None:
            params["max_days_old"] = str(self.max_days_old)
        return params

    @retry_policy
    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        if not settings.adzuna_app_id or not settings.adzuna_app_key:
            raise RuntimeError(
                "Adzuna credentials missing — set ADZUNA_APP_ID and ADZUNA_APP_KEY in .env"
            )

        url = self.source_url
        host = urlparse(url).netloc
        client = get_client(host)
        limiter = get_limiter(host)

        async with limiter:
            response = await client.get(url, params=self._params())

        if response.status_code >= 400:
            response.raise_for_status()

        data = response.json()
        raw_jobs = data.get("results", []) or []
        jobs = [self._parse_job(j) for j in raw_jobs if isinstance(j, dict)]

        return FetchResult(jobs=jobs, status_code=response.status_code)

    def _parse_job(self, raw: dict) -> NormalizedJob:
        desc_text = raw.get("description", "") or ""
        title = raw.get("title", "Unknown") or "Unknown"
        company_obj = raw.get("company") or {}
        company = company_obj.get("display_name") or self.company_name
        location_obj = raw.get("location") or {}
        location_str = location_obj.get("display_name") or ""

        salary_min = _to_int(raw.get("salary_min"))
        salary_max = _to_int(raw.get("salary_max"))
        currency = _currency_for_country(self.country)

        return NormalizedJob(
            external_id=str(raw.get("id") or raw.get("redirect_url") or title),
            title=title,
            company=company,
            apply_url=raw.get("redirect_url", "") or "",
            description_html="",
            description_text=html_to_text(desc_text),
            location=normalise_location(location_str) if location_str else None,
            remote=is_remote(location_str, desc_text),
            employment_type=raw.get("contract_type"),
            seniority=infer_seniority(title),
            salary_min=salary_min,
            salary_max=salary_max,
            salary_currency=currency,
            posted_at=_parse_created(raw.get("created")),
            raw_payload=raw,
        )


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        n = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if n <= 0 or n > 10_000_000:
        return None
    return n


def _parse_created(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


_COUNTRY_CURRENCY = {
    "us": "USD",
    "gb": "GBP",
    "au": "AUD",
    "ca": "CAD",
    "de": "EUR",
    "fr": "EUR",
    "nl": "EUR",
    "at": "EUR",
    "pl": "PLN",
    "in": "INR",
    "sg": "SGD",
    "nz": "NZD",
    "za": "ZAR",
    "br": "BRL",
    "mx": "MXN",
    "it": "EUR",
    "es": "EUR",
    "ch": "CHF",
}


def _currency_for_country(code: str) -> str:
    return _COUNTRY_CURRENCY.get(code.lower(), "USD")
