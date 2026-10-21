"""Title allow/deny filters for DE / AI-ML / FDE (ingest + UI).

Plain SWE/SDE titles can be rescued by scanning the JD for data/ML signals.
Titles that already hit DE/AIML/FDE includes never pay that JD scan.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from jobtracker.config import settings
from jobtracker.normalize.seniority import infer_seniority

_NEW_GRAD_DATA_AI = (
    r"(?:machine\s+learning|\bml\b|\bai\b|data\s+engineer|data\s+scien|"
    r"analytics|forward\s+deployed|\bfde\b|mlops|applied\s+scientist)"
)
_EARLY_TALENT = (
    r"(?:new\s+grad(?:uate)?|university\s+grad(?:uate)?|early\s+career|"
    r"early\s+talent|emerging\s+talent|futureforce|"
    r"class\s+of\s+202[67]|\b202[67]\b|\bjunior\b|\bintern(?:ship)?\b)"
)
_SWE_FAMILY = (
    r"(?:software\s+engineer|software\s+developer|"
    r"software\s+development\s+engineer|\bswe\b|\bsde\b)"
)


def _contains_keyword(haystack: str, needle: str) -> bool:
    """Match keyword in title; short tokens use boundaries (avoid 'iv' in university)."""
    raw = (needle or "").lower()
    if not raw.strip():
        return False
    token = raw.strip()
    # Short / roman / spaced tokens need boundaries. Longer phrases use substring.
    needs_boundary = (
        len(token) <= 4
        or raw != token  # intentional leading/trailing space in config
        or token in {"lead", "staff", "chief", "intern", "coop", "mobile", "android"}
    )
    if needs_boundary:
        return (
            re.search(
                r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])",
                haystack,
            )
            is not None
        )
    return token in haystack


def _has_any(haystack: str, needles: list[str]) -> bool:
    return any(_contains_keyword(haystack, n) for n in needles if n and str(n).strip())


@lru_cache(maxsize=1)
def load_title_filters() -> dict[str, Any]:
    path = Path(settings.config_dir) / "title_filters.yaml"
    if not path.exists():
        return {"enabled": False}
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {"enabled": False}


def company_excluded(company: str | None) -> bool:
    """True when the company is on the exclude_companies blocklist."""
    cfg = load_title_filters()
    name = (company or "").lower()
    return any(c and str(c).lower() in name for c in (cfg.get("exclude_companies") or []))


def clear_title_filter_cache() -> None:
    load_title_filters.cache_clear()


def _is_early_swe_title(title: str) -> bool:
    return bool(
        re.search(
            rf"{_EARLY_TALENT}.{{0,50}}{_SWE_FAMILY}|{_SWE_FAMILY}.{{0,50}}{_EARLY_TALENT}",
            title,
            re.I | re.S,
        )
    )


def _is_data_title(title: str, include_titles: list[str]) -> bool:
    if include_titles and _has_any(title, include_titles):
        return True
    if re.search(
        rf"(new\s+grad(?:uate)?|university\s+grad(?:uate)?|graduate)\b.{{0,40}}\b{_NEW_GRAD_DATA_AI}",
        title,
        re.I | re.S,
    ):
        return True
    if re.search(
        rf"\b{_NEW_GRAD_DATA_AI}\b.{{0,40}}\b"
        r"(new\s+grad(?:uate)?|university\s+grad(?:uate)?|graduate)\b",
        title,
        re.I | re.S,
    ):
        return True
    return False


def _title_matches_include(title: str, include_titles: list[str]) -> bool:
    if not include_titles:
        return True
    return _is_data_title(title, include_titles) or _is_early_swe_title(title)


def role_lane(title: str | None) -> str:
    """Split board: data (DE/AIML/FDE) vs SWE new-grad vs other.

    Data wins when both match (e.g. Software Engineer, Data Platform).
    """
    text = (title or "").strip().lower()
    if not text:
        return "other"
    include = list((load_title_filters().get("include_title_keywords") or []))
    if _is_data_title(text, include):
        return "data"
    if _is_early_swe_title(text):
        return "swe_ng"
    return "other"


def _jd_rescue_keywords(cfg: dict[str, Any]) -> list[str]:
    explicit = list(cfg.get("jd_rescue_keywords") or [])
    if explicit:
        return explicit
    # Default: same signals as title includes (data / ML / FDE phrases in the body).
    return list(cfg.get("include_title_keywords") or [])


def _jd_rescues(description: str | None, cfg: dict[str, Any]) -> bool:
    """True when JD has DE/AIML/FDE signal. Caller must already know title needs rescue."""
    if not description or not str(description).strip():
        return False
    if not cfg.get("jd_rescue_enabled", True):
        return False
    keywords = _jd_rescue_keywords(cfg)
    if not keywords:
        return False
    blob = str(description).lower()
    # Cap scan cost — rescue signals almost always appear early in the JD.
    blob = blob[:12000]
    return _has_any(blob, keywords)


def is_jd_rescue_candidate(title: str | None, *, seniority: str | None = None) -> bool:
    """Soft-excluded SWE/SDE that could still pass after a JD scan (not hard-blocked)."""
    cfg = load_title_filters()
    if not cfg.get("enabled", True):
        return False

    text = (title or "").strip().lower()
    if not text:
        return False

    exclude_titles = list(cfg.get("exclude_title_keywords") or [])
    if exclude_titles and _has_any(text, exclude_titles):
        return False

    exclude_seniority = {str(x).strip().lower() for x in (cfg.get("exclude_seniority") or []) if x}
    level = (seniority or infer_seniority(title or "") or "").strip().lower()
    if level and level in exclude_seniority:
        return False

    include_titles = list(cfg.get("include_title_keywords") or [])
    has_include = _title_matches_include(text, include_titles) if include_titles else True
    if has_include:
        return False  # already DE/AIML/FDE — no JD scan

    soft_exclude = list(cfg.get("soft_exclude_title_keywords") or [])
    return bool(soft_exclude and _has_any(text, soft_exclude))


def title_filter_reason(
    title: str | None,
    *,
    seniority: str | None = None,
    description: str | None = None,
) -> str | None:
    """Return reject reason, or None if the title should be kept.

    JD is only consulted for soft-excluded SWE/SDE titles. DE/AIML/FDE titles
    that already match include keywords skip the description scan.
    """
    cfg = load_title_filters()
    if not cfg.get("enabled", True):
        return None

    text = (title or "").strip().lower()
    if not text:
        return "empty_title"

    include_titles = list(cfg.get("include_title_keywords") or [])
    has_include = _title_matches_include(text, include_titles) if include_titles else True

    exclude_titles = list(cfg.get("exclude_title_keywords") or [])
    if exclude_titles and _has_any(text, exclude_titles):
        return "exclude_title"

    soft_exclude = list(cfg.get("soft_exclude_title_keywords") or [])
    soft_hit = bool(soft_exclude and _has_any(text, soft_exclude) and not has_include)
    if soft_hit:
        if _jd_rescues(description, cfg):
            pass  # rescued via JD — fall through to seniority check
        else:
            return "exclude_title"

    if include_titles and not has_include and not soft_hit:
        return "missing_include"

    exclude_seniority = {str(x).strip().lower() for x in (cfg.get("exclude_seniority") or []) if x}
    level = (seniority or infer_seniority(title or "") or "").strip().lower()
    if level and level in exclude_seniority:
        return f"exclude_seniority:{level}"

    return None


def passes_title_filter(
    title: str | None,
    *,
    seniority: str | None = None,
    description: str | None = None,
) -> bool:
    return title_filter_reason(title, seniority=seniority, description=description) is None


def keep_for_detail_fetch(title: str | None, *, seniority: str | None = None) -> bool:
    """Two-phase list filter: keep passes + soft SWE that need a JD before deciding."""
    return passes_title_filter(title, seniority=seniority) or is_jd_rescue_candidate(
        title, seniority=seniority
    )
