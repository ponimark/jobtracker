"""Fast HTML-to-plain-text using selectolax (lexbor backend)."""
import re

from selectolax.lexbor import LexborHTMLParser


def html_to_text(html: str | None) -> str:
    """Strip HTML tags and normalise whitespace. Returns empty string for None."""
    if not html:
        return ""
    parser = LexborHTMLParser(html)
    # Remove script and style nodes entirely
    for tag in parser.css("script, style, noscript"):
        tag.decompose()
    text = parser.body.text(separator=" ", strip=True) if parser.body else ""
    return _clean_whitespace(text)


def truncate_text(text: str, max_chars: int = 2000) -> str:
    """Truncate to max_chars at a word boundary."""
    if len(text) <= max_chars:
        return text
    # If the character at max_chars is a space or we're at the end, we're already at a boundary
    if len(text) == max_chars or text[max_chars] == " ":
        return text[:max_chars]
    # Otherwise cut back to the last space to avoid splitting a word
    truncated = text[:max_chars]
    last_space = truncated.rfind(" ")
    return truncated[:last_space] if last_space > 0 else truncated


def _clean_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
