from jobtracker.normalize.experience import (
    meets_experience_requirement,
    parse_experience,
)


def test_parse_experience_range() -> None:
    parsed = parse_experience("We need 3-5 years of experience in Python and SQL.")
    assert parsed.min_years == 3
    assert parsed.max_years == 5


def test_parse_experience_plus() -> None:
    parsed = parse_experience("5+ years of experience with Airflow.")
    assert parsed.min_years == 5
    assert parsed.max_years is None


def test_parse_experience_single_years() -> None:
    parsed = parse_experience("At least 2 years working with Spark.")
    assert parsed.min_years == 2
    assert parsed.max_years == 2


def test_parse_experience_plus_experience_phrase() -> None:
    parsed = parse_experience("2+ of experience shipping high-quality architectures for critical systems preferred.")
    assert parsed.min_years == 2
    assert parsed.max_years is None


def test_meets_experience_requirement() -> None:
    assert meets_experience_requirement(3, 5) is True
    assert meets_experience_requirement(5, 2) is False
    assert meets_experience_requirement(None, 2) is True
