"""Abstract base for all job source adapters."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class NormalizedJob:
    external_id: str
    title: str
    company: str
    apply_url: str
    description_html: str = ""
    description_text: str = ""
    location: str | None = None
    remote: bool | None = None
    employment_type: str | None = None
    seniority: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    posted_at: datetime | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    jobs: list[NormalizedJob]
    status_code: int
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False  # True = 304, skip processing


class SourceAdapter(ABC):
    """Every source adapter must implement fetch() -> FetchResult.

    Adapters where description retrieval is a separate, expensive network call
    (e.g. aggregators) may opt into two-phase fetch by setting
    ``supports_two_phase = True`` and implementing ``fetch_list()`` +
    ``fetch_details_for()``. The worker will then:

        1. call ``fetch_list()`` for cheap metadata only
        2. dedup against Redis using ``external_id``
        3. call ``fetch_details_for()`` on the *new* jobs only

    This lets adapters turn on description fetching by default without paying
    for details on jobs we've already seen.
    """

    ats: str  # class-level identifier, e.g. "greenhouse"
    supports_two_phase: bool = False

    def __init__(self, slug: str, company_name: str | None = None, **kwargs: Any) -> None:
        self.slug = slug
        self.company_name = company_name or slug
        self.extra = kwargs

    @abstractmethod
    async def fetch(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Fetch and normalise jobs from this source."""
        ...

    async def fetch_list(
        self,
        last_etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        """Two-phase step 1: return jobs with metadata only (no descriptions).

        Only called when ``supports_two_phase`` is True. Default raises.
        """
        raise NotImplementedError

    async def fetch_details_for(self, jobs: list[NormalizedJob]) -> None:
        """Two-phase step 2: populate ``description_html``/``description_text``.

        Mutates the passed jobs in place. Only called when
        ``supports_two_phase`` is True. Default raises.
        """
        raise NotImplementedError

    @property
    def source_url(self) -> str:
        """The canonical URL polled for this source (used for ETag keying)."""
        raise NotImplementedError
