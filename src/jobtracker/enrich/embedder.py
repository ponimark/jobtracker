"""sentence-transformers wrapper for BGE-small embeddings."""
import time

from sentence_transformers import SentenceTransformer

from jobtracker.config import settings
from jobtracker.logging import get_logger
from jobtracker.metrics.prometheus import EMBED_DURATION

log = get_logger(__name__)

_BGE_QUERY_PREFIX = "Represent this query for retrieving relevant job postings: "

_REQ_HEADER_PHRASES: tuple[str, ...] = (
    "what you'll do", "what you will do",
    "what you'll need", "what you will need", "what you need",
    "responsibilities", "requirements", "qualifications",
    "must have", "must haves", "ideal candidate",
    "desired qualifications", "basic qualifications", "minimum qualifications",
    "who you are", "about you", "your impact",
)
_REQ_END_PHRASES: tuple[str, ...] = (
    "nice to have", "preferred qualifications", "bonus points",
    "pay transparency", "equal opportunity", "equal employment",
    "salary range", "compensation range", "base salary",
    "benefits", "perks", "why join", "why we love",
    "by applying", "privacy policy", "background check",
    "e-verify", "eeo", "affirmative action",
)


def _extract_requirements_blob(text: str) -> str | None:
    """Find the requirements section inside flat/collapsed text by phrase anchors."""
    if not text:
        return None
    lower = text.lower()
    start = -1
    for phrase in _REQ_HEADER_PHRASES:
        idx = lower.find(phrase)
        if idx != -1 and (start == -1 or idx < start):
            start = idx
    if start == -1:
        return None
    end = len(text)
    for phrase in _REQ_END_PHRASES:
        idx = lower.find(phrase, start + 1)
        if idx != -1 and idx < end:
            end = idx
    blob = text[start:end].strip()
    if len(blob) < 120:
        return None
    return blob

_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("embedder.loading", model=settings.embedding_model, device=device)
        _model = SentenceTransformer(settings.embedding_model, device=device)
        log.info("embedder.ready", device=device)
    return _model


def embed_jobs(texts: list[str]) -> list[list[float]]:
    """Embed a batch of job description texts. Returns normalised float vectors."""
    if not texts:
        return []
    model = _get_model()
    t0 = time.monotonic()
    vectors = model.encode(
        texts,
        batch_size=settings.embedding_batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    elapsed = time.monotonic() - t0
    EMBED_DURATION.observe(elapsed)
    log.debug("embedder.done", count=len(texts), elapsed_s=round(elapsed, 3))
    return vectors.tolist()


def embed_profile(bio: str) -> list[float]:
    """Embed the user profile bio with the BGE query prefix."""
    model = _get_model()
    prefixed = _BGE_QUERY_PREFIX + bio
    vector = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vector.tolist()


def build_job_text(title: str, company: str, description_text: str) -> str:
    """Construct the text fed to the embedder for a job.

    Prefer the requirements block over the raw description, so the embedding
    reflects role requirements rather than company marketing copy.
    """
    from jobtracker.enrich.skills import (
        _extract_requirement_surface,
        _has_requirement_section,
        _normalize_job_text,
    )
    from jobtracker.normalize.html import truncate_text

    normalized = _normalize_job_text(description_text)
    if _has_requirement_section(normalized):
        body_source = _extract_requirement_surface(normalized)
    else:
        blob = _extract_requirements_blob(normalized)
        body_source = blob if blob is not None else normalized
    body = truncate_text(body_source, max_chars=2000)
    return f"{title} at {company}. {body}"
