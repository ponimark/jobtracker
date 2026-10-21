from jobtracker.normalize.title_filter import (
    clear_title_filter_cache,
    is_jd_rescue_candidate,
    keep_for_detail_fetch,
    passes_title_filter,
    role_lane,
    title_filter_reason,
)


def setup_function() -> None:
    clear_title_filter_cache()


def teardown_function() -> None:
    clear_title_filter_cache()


def test_keeps_de_aiml_fde() -> None:
    assert passes_title_filter("Junior Data Engineer")
    assert passes_title_filter("Machine Learning Engineer - University Graduate")
    assert passes_title_filter("Forward Deployed Engineer")
    assert passes_title_filter("AI Engineer")
    assert passes_title_filter("Analytics Engineer")
    assert passes_title_filter("Data Engineer Intern")
    assert passes_title_filter("Machine Learning Internship")


def test_keeps_swe_when_include_also_hits() -> None:
    assert passes_title_filter("Software Engineer, Data Platform")
    assert passes_title_filter("Software Engineer, ML Infra (Junior & New Grad)")
    assert passes_title_filter("AI/ML Software Engineer")
    assert passes_title_filter("SDE, Data Engineer - New Grad")


def test_role_lane_splits_swe_ng_and_data() -> None:
    assert role_lane("Junior Data Engineer") == "data"
    assert role_lane("AI Engineer") == "data"
    assert role_lane("Forward Deployed Engineer") == "data"
    assert role_lane("Software Engineer, Data Platform") == "data"
    assert role_lane("Software Engineer, New Grad") == "swe_ng"
    assert role_lane("Software Engineer - New Grad (2027)") == "swe_ng"
    assert role_lane("Software Engineer, Applied Emerging Talent (2027)") == "swe_ng"
    assert role_lane("Software Engineer, API Frontiers") == "other"
    assert role_lane("Software Engineer") == "other"
    # intern must not match "internal"
    assert role_lane("Software Engineer, Internal Applications - Enterprise") == "other"
    assert role_lane("Software Engineer Intern") == "swe_ng"


def test_keeps_early_career_swe() -> None:
    assert passes_title_filter("Software Engineer, New Grad")
    assert passes_title_filter("Software Engineer, New Grad 2027")
    assert passes_title_filter("University Graduate Software Engineer")
    assert passes_title_filter("Junior Software Developer")
    assert passes_title_filter("Software Engineer Graduate (Data Arch) - 2027 Start")


def test_drops_plain_software_engineer() -> None:
    assert title_filter_reason("Software Engineer") == "exclude_title"
    assert title_filter_reason("Software Engineer II") == "exclude_title"


def test_drops_senior_backend_keeps_intern() -> None:
    assert title_filter_reason("Senior Data Engineer") == "exclude_title"
    # Senior still hard-blocks even with data platform
    assert title_filter_reason("Senior Software Engineer, Data Platform") == "exclude_title"
    assert title_filter_reason("Data Engineer Intern") is None
    assert title_filter_reason("Backend Engineer") in {"exclude_title", "missing_include"}
    assert title_filter_reason("Staff Machine Learning Engineer") == "exclude_title"


def test_drops_unrelated_titles() -> None:
    assert title_filter_reason("Account Executive") == "missing_include"
    assert title_filter_reason("Mechanical Engineer") == "exclude_title"
    # Random titles do not get JD rescue even if JD mentions data.
    assert (
        title_filter_reason(
            "Account Executive",
            description="Build data pipelines and ETL for our customers.",
        )
        == "missing_include"
    )


def test_jd_rescues_soft_swe_only() -> None:
    data_jd = "You will own ETL pipelines, our data platform, and analytics warehouses."
    assert title_filter_reason("Software Engineer", description=data_jd) is None
    assert passes_title_filter("Junior Software Developer", description=data_jd)
    assert title_filter_reason("Software Engineer", description="Write React components.") == "exclude_title"


def test_de_titles_skip_jd_path() -> None:
    # Already included by title — candidate flag false (no JD scan needed).
    assert not is_jd_rescue_candidate("Junior Data Engineer")
    assert is_jd_rescue_candidate("Software Engineer")
    assert not is_jd_rescue_candidate("Senior Software Engineer")
    assert keep_for_detail_fetch("Software Engineer")
    assert not keep_for_detail_fetch("Account Executive")
