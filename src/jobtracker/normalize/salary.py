"""Parse salary ranges from various formats."""
import re
from dataclasses import dataclass

_CURRENCY_SYMBOLS = {"$": "USD", "£": "GBP", "€": "EUR", "¥": "JPY"}
_MULTIPLIERS = {"k": 1_000, "m": 1_000_000}

# Matches: $120k, $120,000, 120000, £80k–£100k, etc.
_RANGE_RE = re.compile(
    r"(?P<sym>[£$€¥])?(?P<lo>[\d,]+)(?P<lo_mult>[km])?(?:\s*[-–—to]+\s*)"
    r"(?P<sym2>[£$€¥])?(?P<hi>[\d,]+)(?P<hi_mult>[km])?",
    re.IGNORECASE,
)
_SINGLE_RE = re.compile(
    r"(?P<sym>[£$€¥])?(?P<val>[\d,]+)(?P<mult>[km])?",
    re.IGNORECASE,
)


@dataclass
class SalaryRange:
    min: int | None = None
    max: int | None = None
    currency: str = "USD"


def parse_salary(text: str | None) -> SalaryRange:
    if not text:
        return SalaryRange()

    text = text.replace(",", "")

    m = _RANGE_RE.search(text)
    if m:
        currency = _CURRENCY_SYMBOLS.get(m.group("sym") or m.group("sym2") or "$", "USD")
        lo = _apply_mult(m.group("lo"), m.group("lo_mult"))
        hi = _apply_mult(m.group("hi"), m.group("hi_mult"))
        # Annualise if values look like monthly/hourly
        lo, hi = _annualise(lo), _annualise(hi)
        return SalaryRange(min=lo, max=hi, currency=currency)

    m2 = _SINGLE_RE.search(text)
    if m2:
        currency = _CURRENCY_SYMBOLS.get(m2.group("sym") or "$", "USD")
        val = _apply_mult(m2.group("val"), m2.group("mult"))
        val = _annualise(val)
        return SalaryRange(min=val, max=val, currency=currency)

    return SalaryRange()


def _apply_mult(digits: str, suffix: str | None) -> int:
    val = int(digits)
    if suffix:
        val *= _MULTIPLIERS.get(suffix.lower(), 1)
    return val


_MAX_SALARY = 10_000_000  # sanity cap — anything above $10M is garbage data


def _annualise(val: int) -> int | None:
    """Heuristically convert hourly/monthly to annual."""
    if val < 500:  # looks hourly (e.g. $75/hr)
        return val * 2080
    if val < 10_000:  # looks monthly
        return val * 12
    if val > _MAX_SALARY:
        return None  # matched a job ID / timestamp, not a real salary
    return val
