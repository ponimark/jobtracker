"""Parse years-of-experience requirements from job text."""
from __future__ import annotations

import re
from urllib.parse import urlparse
from dataclasses import dataclass


@dataclass(frozen=True)
class ExperienceRequirement:
    min_years: int | None = None
    max_years: int | None = None
    raw_text: str | None = None


_YEARS_RE = re.compile(
    r"(?P<min>\d+(?:\.\d+)?)\s*(?:\+|\-|to)\s*(?P<max>\d+(?:\.\d+)?)\s*(?:years?|yrs?|of experience|experience)",
    re.IGNORECASE,
)
_PLUS_RE = re.compile(r"(?P<min>\d+(?:\.\d+)?)\s*\+\s*(?:years?|yrs?|of experience|experience)", re.IGNORECASE)
_SINGLE_RE = re.compile(r"(?P<min>\d+(?:\.\d+)?)\s*(?:years?|yrs?|of experience|experience)", re.IGNORECASE)


def parse_experience(text: str | None) -> ExperienceRequirement:
    """Extract the minimum/maximum years requirement from text."""
    if not text:
        return ExperienceRequirement()

    candidates: list[ExperienceRequirement] = []

    for match in _YEARS_RE.finditer(text):
        min_years = _to_int_years(match.group("min"))
        max_years = _to_int_years(match.group("max"))
        if min_years is not None:
            candidates.append(
                ExperienceRequirement(
                    min_years=min_years,
                    max_years=max_years,
                    raw_text=match.group(0),
                )
            )

    for match in _PLUS_RE.finditer(text):
        min_years = _to_int_years(match.group("min"))
        if min_years is not None:
            candidates.append(
                ExperienceRequirement(
                    min_years=min_years,
                    max_years=None,
                    raw_text=match.group(0),
                )
            )

    # Fall back to single "X years" mentions only if we saw nothing else.
    if not candidates:
        for match in _SINGLE_RE.finditer(text):
            min_years = _to_int_years(match.group("min"))
            if min_years is not None:
                candidates.append(
                    ExperienceRequirement(
                        min_years=min_years,
                        max_years=min_years,
                        raw_text=match.group(0),
                    )
                )

    if not candidates:
        return ExperienceRequirement()

    min_years = max((c.min_years for c in candidates if c.min_years is not None), default=None)
    max_years = max((c.max_years for c in candidates if c.max_years is not None), default=None)
    raw_text = ", ".join(c.raw_text or "" for c in candidates if c.raw_text)
    return ExperienceRequirement(min_years=min_years, max_years=max_years, raw_text=raw_text or None)


async def resolve_experience(
    title: str,
    description_text: str | None,
    description_html: str | None,
    apply_url: str | None = None,
) -> ExperienceRequirement:
    """Parse experience from the board text, then fall back to the job page if needed."""
    base = parse_experience(f"{title}\n{description_text or description_html or ''}")
    if base.min_years is not None or base.max_years is not None or not apply_url:
        return base

    try:
        from jobtracker.http.client import get_client
        from jobtracker.http.ratelimit import get_limiter
        from jobtracker.normalize.html import html_to_text

        host = urlparse(apply_url).netloc
        if not host:
            return base

        client = get_client(host)
        limiter = get_limiter(host)
        async with limiter:
            response = await client.get(apply_url)

        if response.status_code >= 400:
            return base

        page_text = html_to_text(response.text)
        page = parse_experience(f"{title}\n{page_text}")
        if page.min_years is not None or page.max_years is not None:
            return page
    except Exception:
        return base

    return base


def meets_experience_requirement(
    required_min_years: int | None,
    profile_years: int | None,
) -> bool:
    """Return True if the profile meets the minimum required years."""
    if required_min_years is None or profile_years is None:
        return True
    return profile_years >= required_min_years


def _to_int_years(value: str | None) -> int | None:
    if value is None:
        return None
    number = float(value)
    return int(number) if number.is_integer() else int(number) + 1
