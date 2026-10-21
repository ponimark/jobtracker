"""Unit tests for DE/AIML track profile helpers."""

from jobtracker.enrich.track_profiles import (
    ACTIVE_TRACKS,
    TRACK_RESUMES,
    build_profile_json,
    match_sort_key,
)


def test_active_tracks_are_de_and_aiml_only() -> None:
    assert ACTIVE_TRACKS == ("DE", "AIML")
    assert set(TRACK_RESUMES) == {"DE", "AIML"}


def test_build_profile_json_uses_resume_as_bio() -> None:
    text = "Jane Doe\nSkills: Python, SQL, PyTorch\nBuilt ETL pipelines."
    payload = build_profile_json(track="DE", resume_text=text, source="resumes/de.md")
    assert payload["track"] == "DE"
    assert payload["bio"] == text
    assert payload["source"] == "resumes/de.md"
    assert isinstance(payload["skills"], list)


def test_match_sort_key_uses_rerank_when_present() -> None:
    high_rerank = match_sort_key(0.4, 0.4, 0.95)
    low_rerank = match_sort_key(0.4, 0.4, 0.10)
    assert high_rerank > low_rerank
    # Without rerank, vector dominates
    assert match_sort_key(0.1, 0.9, None) > match_sort_key(0.9, 0.1, None)
