"""Infer seniority level from job title."""
import re

_LEVELS: list[tuple[str, list[str]]] = [
    ("intern", ["intern", "internship", "co-op", "coop"]),
    (
        "new_grad",
        [
            "new grad",
            "new graduate",
            "university graduate",
            "university grad",
            "campus hire",
            "graduate program",
            "grad program",
        ],
    ),
    (
        "junior",
        ["junior", "jr ", "entry", "associate", "early career", "entry-level", "entry level"],
    ),
    ("mid", ["mid-level", "mid level", "ii ", "level 2"]),
    ("senior", ["senior", "sr ", "sr.", "level 3", "level iii"]),
    ("staff", ["staff", "level 4", "level iv"]),
    ("principal", ["principal", "level 5", "level v", "distinguished"]),
    ("lead", ["lead", "tech lead", "team lead"]),
    ("manager", ["manager", "engineering manager", "em "]),
    ("director", ["director", "vp ", "vice president", "head of"]),
]


def infer_seniority(title: str) -> str | None:
    """Return the best-matching seniority label or None."""
    lower = title.lower()
    for level, patterns in _LEVELS:
        for pat in patterns:
            token = pat.strip()
            if not token:
                continue
            # Require a full token boundary on both sides so "lead" does not
            # match inside "learning" / "leadership" false-positives are ok to miss.
            if re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", lower):
                return level
    return None


def matches_seniority(title: str, wanted: list[str]) -> bool:
    """Return True if the inferred seniority is in the wanted list."""
    if not wanted:
        return True
    inferred = infer_seniority(title)
    return inferred in wanted if inferred else True  # unknown = don't filter
