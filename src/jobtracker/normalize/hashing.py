"""xxhash-based content and canonical fingerprinting."""
import re

import xxhash

# Legal / marketing suffixes that differ across Greenhouse vs JobSpy/Adzuna.
_COMPANY_SUFFIXES = re.compile(
    r"\b(incorporated|corporation|company|platforms|limited|llc|ltd|inc|corp|co)\b"
)


def canonical_hash(
    title: str,
    company: str,
    location: str | None,
    employment_type: str | None = None,
    seniority: str | None = None,
) -> bytes:
    """
    Stable identity hash across sources for the same role.

    Location is intentionally ignored: multi-city postings of the same title
    at the same company collapse via job_aliases so the board shows one card.
    The ``location`` argument is kept for call-site compatibility.
    """
    del location  # not part of identity — see docstring
    parts = [
        _normalise(title),
        _normalise_company(company),
        _normalise(employment_type or ""),
        _normalise(seniority or ""),
    ]
    key = "|".join(parts)
    return xxhash.xxh64(key).digest()


def content_hash(description: str) -> bytes:
    """Hash of job description — detects edits so we re-embed changed jobs."""
    return xxhash.xxh64(description.strip()).digest()


def _normalise(text: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation for stable comparison."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _normalise_company(text: str) -> str:
    """Like ``_normalise``, plus strip Inc/LLC/Corp so source variants match."""
    text = _normalise(text)
    text = _COMPANY_SUFFIXES.sub("", text)
    return re.sub(r"\s+", " ", text).strip()
