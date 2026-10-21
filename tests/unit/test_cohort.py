"""Cohort timing tags and title prefixes."""

from jobtracker.normalize.cohort import (
    classify_cohort_timing,
    is_new_grad_cohort,
    with_cohort_title_prefix,
)


def test_explicit_2027_from_title() -> None:
    out = classify_cohort_timing("Data Engineer - 2027 Start", "")
    assert out["cohortTiming"] == "explicit_2027"
    assert with_cohort_title_prefix("Data Engineer - 2027 Start", out["cohortTiming"]).startswith(
        "[2027]"
    )


def test_likely_new_grad() -> None:
    out = classify_cohort_timing("New Grad Machine Learning Engineer", "")
    assert out["cohortTiming"] == "likely_new_grad"
    assert is_new_grad_cohort(out["cohortTiming"])
    assert with_cohort_title_prefix("New Grad ML Engineer", "likely_new_grad") == (
        "[New Grad] New Grad ML Engineer"
    )


def test_early_career() -> None:
    out = classify_cohort_timing("Junior Data Engineer", "")
    assert out["cohortTiming"] == "early_career"
    assert not is_new_grad_cohort(out["cohortTiming"])
    assert with_cohort_title_prefix("Junior Data Engineer", "early_career").startswith("[Early]")


def test_prefix_idempotent() -> None:
    once = with_cohort_title_prefix("[2027] SWE Grad", "explicit_2027")
    assert once == "[2027] SWE Grad"


def test_unknown() -> None:
    out = classify_cohort_timing("Staff Data Engineer", "5+ years required")
    assert out["cohortTiming"] == "unknown"
    assert with_cohort_title_prefix("Staff Data Engineer", "unknown") == "Staff Data Engineer"
