"""Parse remote/location strings from job postings."""
import re

_REMOTE_PATTERNS = [
    r"\bremote\b",
    r"\bwork from home\b",
    r"\bwfh\b",
    r"\bfully remote\b",
    r"\b100%\s*remote\b",
    r"\bdistributed\b",
]

_REMOTE_RE = re.compile("|".join(_REMOTE_PATTERNS), re.IGNORECASE)

_ONSITE_PATTERNS = [
    r"\bon.?site\b",
    r"\bin.?office\b",
    r"\bno remote\b",
    r"\bin person\b",
]
_ONSITE_RE = re.compile("|".join(_ONSITE_PATTERNS), re.IGNORECASE)

_US_LOCATION_PATTERNS = [
    r"\bremote[-\s]*us\b",
    r"\bremote[-\s]*usa\b",
    r"\busa\b",
    r"\bunited states\b",
    r"\bus[-\s]*only\b",
    r"\b(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b",
    r"california",
    r"washington",
    r"new york",
    r"texas",
    r"seattle",
    r"san francisco",
    r"chicago",
    r"boston",
    r"atlanta",
    r"denver",
    r"austin",
    r"portland",
    r"los angeles",
    r"mountain view",
    r"palo alto",
    r"menlo park",
    r"bellevue",
    r"new jersey",
    r"north carolina",
    r"georgia",
    r"illinois",
    r"massachusetts",
    r"colorado",
    r"virginia",
]

_NON_US_LOCATION_PATTERNS = [
    r"\bpoland\b",
    r"\bcanada\b",
    r"\bunited kingdom\b",
    r"\buk\b",
    r"\bengland\b",
    r"\blondon\b",
    r"\bscotland\b",
    r"\bwales\b",
    r"\birland\b",
    r"\bgermany\b",
    r"\bfrance\b",
    r"\bnetherlands\b",
    r"\baustralia\b",
    r"\bnew zealand\b",
    r"\bindia\b",
    r"\bchina\b",
    r"\bjapan\b",
    r"\bsouth korea\b",
    r"\bkorea\b",
    r"\bslovenia\b",
    r"\btoronto\b",
    r"\bmontreal\b",
    r"\bvancouver\b",
    r"\bljubljana\b",
    r"\bmelbourne\b",
    r"\bsydney\b",
    r"\bbengaluru\b",
    r"\bparis\b",
    r"\bmunich\b",
    r"\bcolombia\b",
    r"\bmexico\b",
    r"\bbrazil\b",
    r"\bargentina\b",
    r"\bchile\b",
    r"\bperu\b",
    r"\buruguay\b",
    r"\bcosta rica\b",
    r"\bsao paulo\b",
    r"\bmexico city\b",
    r"\bbogota\b",
    r"\bdubai\b",
    r"\bisrael\b",
    r"\btel aviv\b",
    r"\begypt\b",
    r"\bsouth africa\b",
    r"\bcape town\b",
    r"\bsingapore\b",
    r"\bhong kong\b",
    r"\bshanghai\b",
    r"\bbeijing\b",
    r"\btokyo\b",
    r"\bseoul\b",
    r"\bwarsaw\b",
    r"\bprague\b",
    r"\bbarcelona\b",
    r"\bmadrid\b",
    r"\bspain\b",
    r"\bitaly\b",
    r"\bportugal\b",
    r"\bsweden\b",
    r"\bnorway\b",
    r"\bdenmark\b",
    r"\bfinland\b",
    r"\bturkey\b",
    r"\bphilippines\b",
    r"\bpakistan\b",
    r"\bvietnam\b",
    r"\bindonesia\b",
    r"\bthailand\b",
    r"\bmalaysia\b",
    r"\beurope\b",
    r"\bemea\b",
    r"\bapac\b",
    r"\blatam\b",
]

_US_RE = re.compile("|".join(_US_LOCATION_PATTERNS), re.IGNORECASE)
_NON_US_RE = re.compile("|".join(_NON_US_LOCATION_PATTERNS), re.IGNORECASE)


def is_remote(location: str | None, description: str | None = None) -> bool | None:
    """
    Returns True if clearly remote, False if clearly on-site, None if ambiguous.
    Checks location field first, then description as fallback.
    """
    for text in filter(None, [location, description]):
        if _REMOTE_RE.search(text):
            return True
        if _ONSITE_RE.search(text):
            return False
    return None


def normalise_location(location: str | None) -> str | None:
    """Return a cleaned location string, or None if empty."""
    if not location:
        return None
    location = re.sub(r"\s+", " ", location).strip()
    return location or None


def is_us_location(location: str | None, description: str | None = None) -> bool:
    """
    Return True when the posting appears to be US-based.

    We keep this conservative:
    - explicit foreign locations are rejected
    - generic "Remote" is not enough by itself
    - US markers in location or description are accepted
    """
    location_text = location or ""
    description_text = description or ""

    if _NON_US_RE.search(location_text):
        return False
    if _US_RE.search(location_text):
        return True

    # Generic remote roles only pass if the description explicitly says US/USA.
    if _REMOTE_RE.search(location_text) and _US_RE.search(description_text) and not _NON_US_RE.search(description_text):
        return True

    return False
