"""Standalone mini web server for the browser bookmarklet.

Reads resumes from `resumes/*.md`, exposes POST /score which accepts a JD
text blob and returns per-resume keyword + vector cosine scores plus missing
skills.

Uses the bi-encoder (BGE-small) from the main pipeline — embeds JD and each
resume once, scores via cosine similarity. This gives well-calibrated 0-1
scores where >0.6 = strong match, 0.3-0.5 = weak, <0.2 = irrelevant.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from jobtracker.enrich.embedder import embed_jobs, embed_profile
from jobtracker.enrich.skills import extract_skills, skill_match_summary
from jobtracker.enrich.trim import trim_jd
from jobtracker.logging import configure_logging, get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Resume:
    name: str
    text: str
    skills: tuple[str, ...]
    vector: tuple[float, ...]


def _load_resumes(folder: Path) -> list[Resume]:
    if not folder.exists():
        raise FileNotFoundError(f"Resume folder not found: {folder}")
    resumes: list[Resume] = []
    for path in sorted(folder.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        vector = tuple(embed_profile(text))
        resumes.append(
            Resume(
                name=path.stem,
                text=text,
                skills=tuple(extract_skills(text)),
                vector=vector,
            )
        )
    if not resumes:
        raise RuntimeError(f"No .md resumes found in {folder}")
    return resumes


class ScoreRequest(BaseModel):
    jd: str


class ResumeScore(BaseModel):
    resume: str
    keyword: float
    reranker: float
    missing: list[str]


class ScoreResponse(BaseModel):
    results: list[ResumeScore]
    jd_original_chars: int
    jd_trimmed_chars: int
    jd_trimmed: str


def create_app(resumes_dir: Path | None = None) -> FastAPI:
    configure_logging()
    folder = resumes_dir or Path("resumes")
    resumes = _load_resumes(folder)
    log.info("score_server.loaded", count=len(resumes), names=[r.name for r in resumes])

    app = FastAPI(title="jobtracker score-server")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "resumes": [r.name for r in resumes]}

    @app.post("/score", response_model=ScoreResponse)
    def score(req: ScoreRequest) -> ScoreResponse:
        jd_text = req.jd or ""
        jd_trimmed = trim_jd(jd_text)
        log.info(
            "score.trim",
            jd_original_chars=len(jd_text),
            jd_trimmed_chars=len(jd_trimmed),
        )
        print("\n=== TRIMMED JD ===", flush=True)
        print(jd_trimmed, flush=True)
        print("=== END TRIMMED JD ===\n", flush=True)

        jd_vec = np.asarray(embed_jobs([jd_trimmed])[0], dtype=np.float32)
        results: list[ResumeScore] = []
        for resume in resumes:
            r_vec = np.asarray(resume.vector, dtype=np.float32)
            cos = float(np.dot(jd_vec, r_vec))
            _matched, missing_profile, _missing_master, kw = skill_match_summary(
                jd_text, list(resume.skills)
            )
            results.append(
                ResumeScore(
                    resume=resume.name,
                    keyword=round(kw, 3),
                    reranker=round(cos, 3),
                    missing=missing_profile,
                )
            )
        return ScoreResponse(
            results=results,
            jd_original_chars=len(jd_text),
            jd_trimmed_chars=len(jd_trimmed),
            jd_trimmed=jd_trimmed,
        )

    return app
