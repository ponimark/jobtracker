"""Bootstrap and resolve DE / AIML track profiles from resumes/*.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jobtracker.db.models import UserProfile
from jobtracker.enrich.embedder import embed_profile
from jobtracker.enrich.skills import extract_skills
from jobtracker.logging import get_logger

log = get_logger(__name__)

# Milestone 1: DE + AIML only (FDE later).
TRACK_RESUMES: dict[str, str] = {
    "DE": "de.md",
    "AIML": "ai.md",
}

ACTIVE_TRACKS: tuple[str, ...] = tuple(TRACK_RESUMES.keys())


def resume_path(track: str, resumes_dir: Path) -> Path:
    filename = TRACK_RESUMES[track]
    return resumes_dir / filename


def build_profile_json(*, track: str, resume_text: str, source: str) -> dict:
    skills = sorted(extract_skills(resume_text))
    return {
        "track": track,
        "bio": resume_text,
        "skills": skills,
        "source": source,
        "name": track,
    }


async def upsert_track_profile(
    session: AsyncSession,
    *,
    track: str,
    resume_text: str,
    source: str,
) -> UserProfile:
    profile_json = build_profile_json(track=track, resume_text=resume_text, source=source)
    vector = embed_profile(resume_text)

    result = await session.execute(select(UserProfile).where(UserProfile.name == track))
    existing = result.scalar_one_or_none()
    now = datetime.utcnow()

    if existing is None:
        row = UserProfile(
            name=track,
            profile_json=profile_json,
            embedding=vector,
            updated_at=now,
        )
        session.add(row)
        await session.flush()
        log.info("track_profile.created", track=track, skills=len(profile_json["skills"]))
        return row

    existing.profile_json = profile_json
    existing.embedding = vector
    existing.updated_at = now
    await session.flush()
    log.info("track_profile.updated", track=track, skills=len(profile_json["skills"]))
    return existing


async def bootstrap_track_profiles(
    session: AsyncSession,
    *,
    resumes_dir: Path,
    tracks: Iterable[str] | None = None,
) -> list[UserProfile]:
    wanted = list(tracks) if tracks is not None else list(ACTIVE_TRACKS)
    rows: list[UserProfile] = []
    for track in wanted:
        if track not in TRACK_RESUMES:
            raise ValueError(f"Unknown track {track!r}; expected one of {ACTIVE_TRACKS}")
        path = resume_path(track, resumes_dir)
        if not path.exists():
            raise FileNotFoundError(f"Missing resume for track {track}: {path}")
        text = path.read_text(encoding="utf-8")
        rows.append(
            await upsert_track_profile(
                session,
                track=track,
                resume_text=text,
                source=str(path.as_posix()),
            )
        )
    await session.commit()
    return rows


async def load_active_track_profiles(session: AsyncSession) -> list[UserProfile]:
    result = await session.execute(
        select(UserProfile).where(UserProfile.name.in_(list(ACTIVE_TRACKS)))
    )
    profiles = list(result.scalars().all())
    # Stable DE then AIML order
    order = {name: i for i, name in enumerate(ACTIVE_TRACKS)}
    profiles.sort(key=lambda p: order.get(p.name, 99))
    return profiles


def match_sort_key(keyword: float, vector: float, rerank: float | None) -> float:
    """Single scalar for picking the best track on a job."""
    if rerank is not None:
        return 0.5 * float(rerank) + 0.3 * float(vector) + 0.2 * float(keyword)
    return 0.7 * float(vector) + 0.3 * float(keyword)
