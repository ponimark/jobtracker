"""Trim JDs and resumes down to the high-signal portion before reranking.

The cross-encoder has a 512-token input budget per pair. Full JDs + full resumes
blow past that, so the model ends up scoring on a truncated fragment (often the
company boilerplate) and produces near-zero scores. Trimming beforehand keeps
the signal-dense sections and drops the noise.
"""
from __future__ import annotations

import re

_JD_KEEP_HEADERS = (
    r"responsibilit(?:y|ies)",
    r"what you.?ll do",
    r"what you.?ll be doing",
    r"the role",
    r"about the role",
    r"requirements?",
    r"qualifications?",
    r"must[- ]?haves?",
    r"minimum qualifications?",
    r"basic qualifications?",
    r"nice[- ]to[- ]haves?",
    r"preferred qualifications?",
    r"preferred",
    r"you have",
    r"we.?re looking for",
    r"skills?",
    r"experience",
)

_JD_DROP_HEADERS = (
    r"benefits?",
    r"perks?",
    r"compensation",
    r"salary",
    r"pay range",
    r"equal opportunity",
    r"eeo",
    r"diversity",
    r"about (?:us|the company|acme|the team)",
    r"our (?:team|company|mission|values)",
    r"how to apply",
    r"application process",
)

_RESUME_KEEP_HEADERS = (
    r"summary",
    r"profile",
    r"objective",
    r"skills?",
    r"technical skills?",
    r"core competencies",
    r"experience",
    r"work experience",
    r"professional experience",
    r"employment",
    r"projects?",
)

_RESUME_DROP_HEADERS = (
    r"education",
    r"coursework",
    r"certifications?",
    r"awards?",
    r"publications?",
    r"languages",
    r"interests",
    r"hobbies",
    r"references",
    r"volunteer",
)


_HEADER_LINE = re.compile(
    r"^\s{0,4}(?:#+\s*)?([A-Za-z][A-Za-z0-9 &/'-]{2,60}?)\s*:?\s*$",
    re.MULTILINE,
)


def _split_sections(text: str) -> list[tuple[str, str]]:
    """Split text into (header, body) pairs by detected headers.

    The chunk before the first header is returned with header="" so preambles
    aren't lost.
    """
    matches = list(_HEADER_LINE.finditer(text))
    if not matches:
        return [("", text)]
    sections: list[tuple[str, str]] = []
    first = matches[0]
    if first.start() > 0:
        preamble = text[: first.start()].strip()
        if preamble:
            sections.append(("", preamble))
    for i, m in enumerate(matches):
        header = m.group(1).strip().lower()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            sections.append((header, body))
    return sections


def _header_matches(header: str, patterns: tuple[str, ...]) -> bool:
    if not header:
        return False
    for pat in patterns:
        if re.fullmatch(pat, header, re.IGNORECASE):
            return True
    return False


def _fallback_trim(text: str, max_chars: int) -> str:
    """No headers found: drop first paragraph (company blurb) and trailing
    paragraphs (benefits / EEO / apply), keep the middle, hard-cap length."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(paras) <= 2:
        return text[:max_chars].strip()
    middle = paras[1:-1] if len(paras) >= 4 else paras[1:]
    joined = "\n\n".join(middle)
    return joined[:max_chars].strip()


def _trim_with_headers(
    text: str,
    keep: tuple[str, ...],
    drop: tuple[str, ...],
    max_chars: int,
) -> str:
    sections = _split_sections(text)
    if len(sections) <= 1:
        return _fallback_trim(text, max_chars)

    kept: list[str] = []
    for header, body in sections:
        if _header_matches(header, drop):
            continue
        if not header or _header_matches(header, keep):
            piece = f"{header.title()}\n{body}" if header else body
            kept.append(piece)

    if not kept:
        return _fallback_trim(text, max_chars)

    joined = "\n\n".join(kept)
    if len(joined) <= max_chars:
        return joined.strip()
    return joined[:max_chars].strip()


def trim_jd(jd: str, max_chars: int = 1800) -> str:
    """Keep responsibilities/requirements-ish sections, drop benefits/EEO/boilerplate."""
    if not jd:
        return ""
    if len(jd) <= max_chars:
        return jd.strip()
    return _trim_with_headers(jd, _JD_KEEP_HEADERS, _JD_DROP_HEADERS, max_chars)


def trim_resume(resume: str, max_chars: int = 1800) -> str:
    """Keep summary/skills/experience, drop education/certs/hobbies/references."""
    if not resume:
        return ""
    if len(resume) <= max_chars:
        return resume.strip()
    return _trim_with_headers(resume, _RESUME_KEEP_HEADERS, _RESUME_DROP_HEADERS, max_chars)


# --- Short cross-encoder *query* (not full resume) ---------------------------------
# bge-reranker is trained on short queries vs passages. Feeding the full resume as
# the query blows the 512-token pair budget (contact/education dominate) and
# collapses scores near zero even for strong DE↔DE fits.

_CONTACTISH = re.compile(
    r"(?:@|\+?\d[\d\s().-]{7,}|\blinkedin\b|\bgithub\b|https?://)",
    re.IGNORECASE,
)
_SECTION_HEADER = re.compile(
    r"^(EDUCATION|EXPERIENCE|WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|"
    r"PROJECTS?|SKILLS?|TECHNICAL SKILLS?)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
# "Acme | Incoming Data Engineer Intern<TAB>Sept 2026 - Dec 2026"
_ROLE_HEADER = re.compile(
    r"^([^|\n]{2,70}?)\s*\|\s*([^\n\t|]{2,90}?)"
    r"(?:\t.*|\s{2,}.*)?$"
)


def build_rerank_query(
    resume_text: str,
    skills: list[str] | None = None,
    *,
    max_skills: int = 40,
    max_roles: int = 5,
    max_chars: int = 900,
) -> str:
    """Build a short reranker query: summary + role headers + skills.

    Drops contact info, education, project bullets, and long experience bullets.
    """
    text = (resume_text or "").strip()
    if not text and not skills:
        return ""

    parts: list[str] = []
    summary = _extract_summary_line(text)
    if summary:
        parts.append(summary)

    roles = _extract_role_headers(text, max_roles=max_roles)
    if roles:
        parts.append("Experience: " + "; ".join(roles))

    clean_skills = [s.strip() for s in (skills or []) if isinstance(s, str) and s.strip()]
    if clean_skills:
        parts.append("Skills: " + ", ".join(clean_skills[:max_skills]))

    joined = "\n".join(parts).strip()
    if not joined:
        # Last resort: hard-trim resume so we never feed 900+ tokens as query.
        return trim_resume(text, max_chars=max_chars) if text else ""
    if len(joined) > max_chars:
        return joined[:max_chars].rstrip()
    return joined


def _extract_summary_line(resume_text: str) -> str:
    """First non-contact preamble sentence (role summary under the name block)."""
    preamble = _SECTION_HEADER.split(resume_text, maxsplit=1)[0]
    for raw in preamble.splitlines():
        line = raw.strip()
        if not line or len(line) < 40:
            continue
        if _CONTACTISH.search(line):
            continue
        # Skip bare name lines
        if len(line.split()) <= 3 and "|" not in line:
            continue
        return line
    return ""


def _extract_role_headers(resume_text: str, *, max_roles: int) -> list[str]:
    """Company | Title lines from the experience section only."""
    match = re.search(
        r"(?:^|\n)((?:WORK |PROFESSIONAL )?EXPERIENCE)\s*:?\s*\n(.*?)(?=\n(?:EDUCATION|PROJECTS?|SKILLS?|TECHNICAL SKILLS?)\s*:?\s*\n|\Z)",
        resume_text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    body = match.group(2) if match else resume_text
    roles: list[str] = []
    for raw in body.splitlines():
        line = raw.strip()
        if not line or "|" not in line:
            continue
        m = _ROLE_HEADER.match(line)
        if not m:
            continue
        company, title = m.group(1).strip(), m.group(2).strip()
        # Skip long bullet-like lines that happened to contain a pipe
        if len(line) > 120:
            continue
        roles.append(f"{title} at {company}")
        if len(roles) >= max_roles:
            break
    return roles
