from jobtracker.normalize.hashing import canonical_hash, content_hash, _normalise_company


def test_canonical_hash_stable():
    h1 = canonical_hash("Senior Data Engineer", "Acme Corp", "Remote", "Full-time", "senior")
    h2 = canonical_hash("Senior Data Engineer", "Acme Corp", "Remote", "Full-time", "senior")
    assert h1 == h2


def test_canonical_hash_normalises_case():
    h1 = canonical_hash("Senior Data Engineer", "Acme Corp", "Remote", "Full-time", "senior")
    h2 = canonical_hash("SENIOR DATA ENGINEER", "ACME CORP", "REMOTE", "FULL-TIME", "SENIOR")
    assert h1 == h2


def test_canonical_hash_normalises_punctuation():
    h1 = canonical_hash("Senior Data Engineer", "Acme, Corp.", None, None, None)
    h2 = canonical_hash("Senior Data Engineer", "Acme Corp", None, None, None)
    assert h1 == h2


def test_canonical_hash_differs_for_different_titles():
    h1 = canonical_hash("Senior Data Engineer", "Acme", "Remote", "Full-time", "senior")
    h2 = canonical_hash("Staff Data Engineer", "Acme", "Remote", "Full-time", "staff")
    assert h1 != h2


def test_canonical_hash_none_location():
    h1 = canonical_hash("Engineer", "Acme", None, None, None)
    h2 = canonical_hash("Engineer", "Acme", "", "", "")
    assert h1 == h2


def test_canonical_hash_ignores_location() -> None:
    austin = canonical_hash("AI Engineer - FDE", "Databricks", "Austin, TX", "Full-time", None)
    bellevue = canonical_hash("AI Engineer - FDE", "Databricks", "Bellevue, WA", "Full-time", None)
    assert austin == bellevue


def test_canonical_hash_company_suffix_variants() -> None:
    a = canonical_hash("Data Engineer", "Databricks", "Remote", None, None)
    b = canonical_hash("Data Engineer", "Databricks, Inc.", "Seattle", None, None)
    assert a == b
    assert _normalise_company("Meta Platforms, Inc.") == "meta"


def test_canonical_hash_changes_when_employment_type_or_seniority_changes() -> None:
    base = canonical_hash("Data Engineer", "Acme", "Remote", "Full-time", "mid")
    different_type = canonical_hash("Data Engineer", "Acme", "Remote", "Contract", "mid")
    different_seniority = canonical_hash("Data Engineer", "Acme", "Remote", "Full-time", "senior")

    assert base != different_type
    assert base != different_seniority


def test_content_hash_stable():
    h1 = content_hash("We are looking for a data engineer with 5 years experience.")
    h2 = content_hash("We are looking for a data engineer with 5 years experience.")
    assert h1 == h2


def test_content_hash_differs():
    h1 = content_hash("Original description")
    h2 = content_hash("Updated description")
    assert h1 != h2


def test_content_hash_strips_whitespace():
    h1 = content_hash("some description")
    h2 = content_hash("  some description  ")
    assert h1 == h2
