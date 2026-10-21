from jobtracker.enrich.skills import canonicalize_skills, extract_skills, skill_match_summary


def test_extract_skills_uses_master_vocab_and_ignores_generic_words() -> None:
    text = "Join the team to build data pipelines in Python and Apache Airflow."
    assert extract_skills(text) == ["Python", "Airflow"]


def test_canonicalize_skills_collapses_aliases() -> None:
    skills = ["Python", "dbt", "DBT", "Postgres", "postgresql"]
    assert canonicalize_skills(skills) == ["Python", "dbt", "PostgreSQL"]


def test_skill_match_summary_keyword_score_is_job_coverage() -> None:
    # 3 skills in job, 2 match. Denominator is floored at 5 so sparse jobs can't hit 1.00.
    job_text = "We need Python, Airflow, and Spark."
    profile_skills = ["Python", "SQL", "Airflow", "dbt"]

    matched, missing_profile, missing_master, score = skill_match_summary(job_text, profile_skills)

    assert matched == ["Python", "Airflow"]
    assert missing_profile == ["Spark"]
    assert missing_master == []
    assert score == 2 / 5


def test_skill_match_summary_does_not_return_full_score_for_sparse_jobs() -> None:
    # Only 2 detected skills → not enough signal to award a perfect score.
    job_text = "We need Python and Airflow."
    profile_skills = ["Python", "SQL", "Airflow", "dbt"]

    matched, missing_profile, missing_master, score = skill_match_summary(job_text, profile_skills)

    assert matched == ["Python", "Airflow"]
    assert missing_profile == []
    assert missing_master == []
    assert score == 2 / 5


def test_skill_match_summary_can_reach_full_score_on_skill_dense_jobs() -> None:
    # 5 detected skills, all matched → 5/5 = 1.0.
    job_text = "We need Python, SQL, Airflow, dbt, and Spark."
    profile_skills = ["Python", "SQL", "Airflow", "dbt", "Spark"]

    matched, _, _, score = skill_match_summary(job_text, profile_skills)

    assert set(matched) == {"Python", "SQL", "Airflow", "dbt", "Spark"}
    assert score == 1.0


def test_skill_match_summary_strips_company_name_from_job_skills() -> None:
    # A job AT Snowflake that mentions "Snowflake" shouldn't count it as a skill match.
    job_text = "Enterprise Account Executive at Snowflake. Sell Snowflake to customers."
    profile_skills = ["Snowflake", "SQL", "Python"]

    matched, _, _, score = skill_match_summary(
        job_text, profile_skills, company_name="Snowflake"
    )

    assert matched == []
    assert score == 0.0


def test_skill_match_summary_uses_requirements_block_and_cx_vocab() -> None:
    job_text = """
    About the role
    We are building great things.

    What You Need
    4+ years in a relevant field.
    Fluency with both SQL and Python.
    Familiarity with Snowflake, dbt, Dagster, and ETL/reverse ETL tools.
    Experience supporting ERP/HRIS integrations in NetSuite, QuickBooks, Sage Intacct, Xero, or Workday.

    Nice to have
    Customer support and playbooks experience.
    """
    profile_skills = ["Python"]

    matched, missing_profile, missing_master, score = skill_match_summary(job_text, profile_skills)

    assert matched == ["Python"]
    assert "SQL" in missing_profile
    assert "Snowflake" in missing_profile
    # Job-category terms (ERP, HRIS, Customer Support) are intentionally NOT skills.
    assert "ERP" not in missing_profile
    assert "HRIS" not in missing_profile
    assert "Customer Support" not in missing_profile
    # missing_master extraction disabled (aggregator/JobSpy chrome noise)
    assert missing_master == []
    assert score < 0.5


def test_extract_skills_covers_broader_tech_stack_terms() -> None:
    text = """
    Looking for a Data Scientist with statistics, machine learning, and data visualization experience.
    Strong Kubernetes and Go skills are helpful. We also use Next.js, React, Python, SQL, and PostgreSQL.
    """

    skills = extract_skills(text)

    assert "Statistics" in skills
    assert "Machine Learning" in skills
    assert "Data Visualization" in skills
    assert "Kubernetes" in skills
    assert "Go" in skills
    assert "Next.js" in skills
    assert "React" in skills
    assert "Python" in skills
    assert "SQL" in skills
    assert "PostgreSQL" in skills


def test_skill_match_summary_separates_missing_master_terms() -> None:
    job_text = """
    What You Need
    Experience with Python, SQL, dbt, and LookML.
    Familiarity with reverse ETL tools and experimentation platforms.
    """
    profile_skills = ["Python"]

    matched, missing_profile, missing_master, score = skill_match_summary(job_text, profile_skills)

    assert matched == ["Python"]
    assert "SQL" in missing_profile
    assert "dbt" in missing_profile
    assert missing_master == []
    assert score < 0.5


def test_missing_master_disabled_for_noisy_jds() -> None:
    """Board no longer surfaces missing_master; extractor returns empty."""
    job_text = """
    Technology
    Location
    San Jose
    Job Code
    A93037A
    Qualifications
    Minimum Qualifications:
    * Python and PyTorch experience.
    """
    matched, missing_profile, missing_master, score = skill_match_summary(
        job_text, ["Python"]
    )
    assert missing_master == []
    assert "Location" not in missing_master
    assert "Job Code" not in missing_master
