"""Board experience helpers: intern vs new-grad filter flags."""

from types import SimpleNamespace

from jobtracker.web.app import _is_intern


def test_is_intern_from_title() -> None:
    job = SimpleNamespace(seniority=None, employment_type=None, title="Data Engineer Intern")
    assert _is_intern(job, None)


def test_is_intern_from_seniority() -> None:
    job = SimpleNamespace(seniority="intern", employment_type=None, title="Data Engineer")
    assert _is_intern(job, "intern")


def test_is_intern_from_employment_type() -> None:
    job = SimpleNamespace(seniority=None, employment_type="Internship", title="Data Engineer")
    assert _is_intern(job, None)


def test_full_time_new_grad_not_intern() -> None:
    job = SimpleNamespace(
        seniority="new_grad",
        employment_type="Full-time",
        title="Data Engineer New Grad 2027",
    )
    assert not _is_intern(job, "new_grad")
