"""Short cross-encoder query builder (summary + roles + skills)."""

from jobtracker.enrich.trim import build_rerank_query

SAMPLE = """\
JANE DOE
jane.doe@example.com  |  +1 (555) 010-0000 |  LinkedIn  |  GitHub  |  Seattle, WA
Data Engineer with experience building production pipelines and high-performance warehouse systems.
EDUCATION:
University of Washington | MS Information Management (AI & Data Science)	       Sept 2025 - Jun 2027
EXPERIENCE:
Acme | Incoming Data Engineer Intern	Sept 2026 - Dec 2026
Globex | Data Engineer Intern	Jun 2026 - Sept 2026
Moved heavy SQL into dbt models and cut Snowflake query volume 28%.
Initech | Data Engineer Intern	Jan 2025 - May 2025
Built financial pipelines for 3 clients.
PROJECTS
Time Streaming Pipeline
SKILLS
Languages - Python, SQL
"""


def test_build_rerank_query_includes_summary_roles_skills() -> None:
    q = build_rerank_query(
        SAMPLE,
        ["Python", "SQL", "dbt", "Snowflake", "Airflow"],
    )
    assert "Data Engineer with experience" in q
    assert "Incoming Data Engineer Intern at Acme" in q
    assert "Data Engineer Intern at Globex" in q
    assert "Skills: Python, SQL, dbt, Snowflake, Airflow" in q
    # No contact / education dump
    assert "jane.doe" not in q.lower()
    assert "010-0000" not in q
    assert "University of Washington" not in q
    assert "Moved heavy SQL" not in q  # experience bullets dropped
    assert len(q) < 900


def test_build_rerank_query_caps_skills() -> None:
    skills = [f"Skill{i}" for i in range(60)]
    q = build_rerank_query(SAMPLE, skills, max_skills=10)
    assert "Skill0" in q and "Skill9" in q
    assert "Skill10" not in q


def test_build_rerank_query_empty() -> None:
    assert build_rerank_query("", []) == ""
    assert build_rerank_query("", None) == ""
