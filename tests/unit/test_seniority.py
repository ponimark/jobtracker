from jobtracker.normalize.seniority import infer_seniority, matches_seniority


def test_senior():
    assert infer_seniority("Senior Data Engineer") == "senior"
    assert infer_seniority("Sr. Data Engineer") == "senior"


def test_staff():
    assert infer_seniority("Staff Software Engineer") == "staff"


def test_principal():
    assert infer_seniority("Principal Data Engineer") == "principal"


def test_lead():
    assert infer_seniority("Lead Data Engineer") == "lead"


def test_intern():
    assert infer_seniority("Data Engineering Intern") == "intern"


def test_new_grad():
    assert infer_seniority("Data Engineer - New Grad") == "new_grad"
    assert infer_seniority("University Graduate Machine Learning Engineer") == "new_grad"


def test_lead_not_confused_with_learning():
    assert infer_seniority("Machine Learning Engineer") is None
    assert infer_seniority("Lead Data Engineer") == "lead"


def test_matches_seniority_positive():
    assert matches_seniority("Senior Data Engineer", ["senior", "staff"]) is True


def test_matches_seniority_negative():
    assert matches_seniority("Junior Data Engineer", ["senior", "staff"]) is False


def test_matches_seniority_unknown_passthrough():
    # Unknown seniority: don't filter it out
    assert matches_seniority("Data Engineer", ["senior"]) is True


def test_matches_seniority_empty_list():
    assert matches_seniority("Junior Data Engineer", []) is True
