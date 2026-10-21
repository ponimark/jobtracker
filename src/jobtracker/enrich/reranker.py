"""Cross-encoder reranker.

A cross-encoder reads the (profile, job) pair jointly and scores actual relevance,
unlike a bi-encoder which embeds each side independently. Output is a sigmoid-style
relevance score in [0, 1]. Much more discriminating than raw cosine similarity, but
~100x more expensive per pair — so we only run it on the top-K by vector score.
"""
from __future__ import annotations

import time

from sentence_transformers import CrossEncoder

from jobtracker.config import settings
from jobtracker.logging import get_logger

log = get_logger(__name__)

_model: CrossEncoder | None = None


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("reranker.loading", model=settings.reranker_model, device=device)
        _model = CrossEncoder(settings.reranker_model, device=device, max_length=512)
        log.info("reranker.ready", device=device)
    return _model


def rerank_pairs(query: str, docs: list[str]) -> list[float]:
    """Score (query, doc) pairs with the cross-encoder.

    Returns normalized scores in [0, 1] via sigmoid activation.
    """
    if not docs:
        return []
    model = _get_model()
    pairs = [(query, doc) for doc in docs]
    t0 = time.monotonic()
    try:
        scores = model.predict(
            pairs,
            batch_size=settings.reranker_batch_size,
            activation_fn=_sigmoid(),
            show_progress_bar=False,
        )
    except TypeError:
        scores = model.predict(
            pairs,
            batch_size=settings.reranker_batch_size,
            activation_fct=_sigmoid(),
            show_progress_bar=False,
        )
    elapsed = time.monotonic() - t0
    log.debug("reranker.done", count=len(docs), elapsed_s=round(elapsed, 3))
    return [float(s) for s in scores]


def _sigmoid():
    import torch.nn as nn
    return nn.Sigmoid()
