import pytest
from jobtracker.normalize.salary import parse_salary


def test_range_with_k():
    result = parse_salary("$120k–$160k")
    assert result.min == 120_000
    assert result.max == 160_000
    assert result.currency == "USD"


def test_range_no_symbol():
    result = parse_salary("120000 to 160000")
    assert result.min == 120_000
    assert result.max == 160_000


def test_single_value():
    result = parse_salary("$150k")
    assert result.min == 150_000
    assert result.max == 150_000


def test_gbp_symbol():
    result = parse_salary("£80k–£100k")
    assert result.currency == "GBP"
    assert result.min == 80_000


def test_hourly_annualised():
    result = parse_salary("$75/hr")
    assert result.min == 75 * 2080


def test_empty_returns_none():
    result = parse_salary(None)
    assert result.min is None
    assert result.max is None


def test_no_salary_text():
    result = parse_salary("We offer a competitive salary")
    assert result.min is None
