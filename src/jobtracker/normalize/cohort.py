"""Cohort / start-year timing tags (JobSync-style [2027] / [New Grad] / [Early])."""

from __future__ import annotations

import re
from typing import Any

# Highest match wins: explicit_2027 > likely_new_grad > early_career > unknown
_EXPLICIT_2027 = [
    re.compile(r"\bclass of 2027\b", re.I),
    re.compile(r"\b2027\s+start\b", re.I),
    re.compile(
        r"\bstart(?:ing)?\s+(?:in\s+)?"
        r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s*2027\b",
        re.I,
    ),
    re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+2027\b",
        re.I,
    ),
    re.compile(r"\b(?:spring|summer|fall|autumn|winter)\s+2027\b", re.I),
    re.compile(r"\bgraduat(?:e|ing|ion)\b.{0,40}\b2027\b", re.I | re.S),
    re.compile(r"\b2027\b.{0,40}\bgraduat", re.I | re.S),
    re.compile(r"\bavailable\b.{0,30}\b2027\b", re.I | re.S),
    re.compile(r"\bstart date\b.{0,40}\b2027\b", re.I | re.S),
    re.compile(
        r"\b(?:dec(?:ember)?|nov(?:ember)?)\s*2026\b.{0,40}\b(?:jun(?:e)?|may|july)\s*2027\b",
        re.I | re.S,
    ),
    re.compile(r"\bbetween\b.{0,20}\b2026\b.{0,20}\b2027\b", re.I | re.S),
]

_LIKELY_NEW_GRAD = [
    re.compile(r"\buniversity\s+graduate\b", re.I),
    re.compile(r"\bnew\s+grad(?:uate)?\b", re.I),
    re.compile(r"\bearly\s+career\b", re.I),
    re.compile(r"\bcampus\s+(?:hire|recruit|program|graduate)\b", re.I),
    re.compile(r"\bgraduate\s+(?:software|data|ml|machine learning)?\s*engineer\b", re.I),
    re.compile(r"\bsoftware\s+engineer\s*[-,]?\s*university\b", re.I),
    re.compile(r"\bnew\s+graduate\s+engineer\b", re.I),
    re.compile(r"\buniversity\s+grad\b", re.I),
    re.compile(r"\bgrad(?:uate)?\s+program\b", re.I),
]

_EARLY_CAREER = [
    re.compile(r"\bjunior\b", re.I),
    re.compile(r"\bentry[-\s]?level\b", re.I),
    re.compile(r"\bassociate\s+(?:software|data|engineer)\b", re.I),
    re.compile(r"\b0\s*[-–—to]+\s*1\s*\+?\s*years?\b", re.I),
    re.compile(r"\b0\s*[-–—to]+\s*2\s*\+?\s*years?\b", re.I),
]

COHORT_TAG_LABELS = {
    "explicit_2027": "2027 Start",
    "likely_new_grad": "New Grad",
    "early_career": "Early Career",
    "unknown": "Cohort Unknown",
}

COHORT_TITLE_PREFIXES = {
    "explicit_2027": "[2027]",
    "likely_new_grad": "[New Grad]",
    "early_career": "[Early]",
}

# Experience-filter "new_grad" matches these cohort values (+ junior seniority).
# Internships use a separate Experience dropdown value ("intern").
NEW_GRAD_COHORTS = frozenset({"explicit_2027", "likely_new_grad"})

_TITLE_PREFIX_RE: re.Pattern[str] | None = None


def _normalize_desc(text: str) -> str:
    return text.replace("\\+", "+").replace("\\-", "-").replace("\\*", "*")


def classify_cohort_timing(title: str = "", description: str = "") -> dict[str, Any]:
    """Return cohortTiming + evidence from title/description."""
    title_l = (title or "").strip()
    blob = _normalize_desc(f"{title_l}\n{description or ''}")

    for pattern in _EXPLICIT_2027:
        m = pattern.search(blob)
        if m:
            return {
                "cohortTiming": "explicit_2027",
                "cohortTimingEvidence": m.group(0).strip()[:120],
            }
    for pattern in _LIKELY_NEW_GRAD:
        m = pattern.search(blob)
        if m:
            return {
                "cohortTiming": "likely_new_grad",
                "cohortTimingEvidence": m.group(0).strip()[:120],
            }
    for pattern in _EARLY_CAREER:
        m = pattern.search(blob)
        if m:
            return {
                "cohortTiming": "early_career",
                "cohortTimingEvidence": m.group(0).strip()[:120],
            }
    return {
        "cohortTiming": "unknown",
        "cohortTimingEvidence": "no 2027/new-grad/early-career timing signal found",
    }


def cohort_tag(cohort_timing: str | None) -> str | None:
    if not cohort_timing or cohort_timing == "unknown":
        return None
    return COHORT_TAG_LABELS.get(str(cohort_timing).strip())


def cohort_title_prefix(cohort_timing: str | None) -> str | None:
    if not cohort_timing:
        return None
    return COHORT_TITLE_PREFIXES.get(str(cohort_timing).strip())


def _title_prefix_pattern() -> re.Pattern[str]:
    global _TITLE_PREFIX_RE
    if _TITLE_PREFIX_RE is None:
        labels = sorted(
            {
                *[COHORT_TAG_LABELS[k] for k in COHORT_TITLE_PREFIXES],
                *COHORT_TITLE_PREFIXES.values(),
            },
            key=len,
            reverse=True,
        )
        escaped = "|".join(re.escape(x.strip("[]")) for x in labels)
        _TITLE_PREFIX_RE = re.compile(rf"^\[(?:{escaped})\]\s*", re.IGNORECASE)
    return _TITLE_PREFIX_RE


def with_cohort_title_prefix(title: str | None, cohort_timing: str | None) -> str:
    """Prefix title for list visibility; idempotent."""
    text = str(title or "").strip()
    text = _title_prefix_pattern().sub("", text).strip()
    prefix = cohort_title_prefix(cohort_timing)
    if not prefix:
        return text
    return f"{prefix} {text}"


def is_new_grad_cohort(cohort_timing: str | None) -> bool:
    return (cohort_timing or "") in NEW_GRAD_COHORTS
