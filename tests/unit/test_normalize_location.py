from jobtracker.normalize.location import is_remote, is_us_location, normalise_location


def test_remote_keyword():
    assert is_remote("Remote") is True
    assert is_remote("remote") is True
    assert is_remote("Fully Remote") is True
    assert is_remote("100% Remote") is True


def test_onsite_keyword():
    assert is_remote("On-site, New York") is False
    assert is_remote("In-office only") is False


def test_ambiguous_returns_none():
    assert is_remote("San Francisco, CA") is None
    assert is_remote(None) is None


def test_description_fallback():
    assert is_remote(None, "This is a fully remote position") is True
    assert is_remote(None, "This role requires on-site presence") is False


def test_location_wins_over_description():
    # Location says remote, description says on-site → remote wins (checked first)
    assert is_remote("Remote", "Must be on-site 3 days/week") is True


def test_normalise_strips_whitespace():
    assert normalise_location("  New York  ") == "New York"


def test_normalise_empty_returns_none():
    assert normalise_location("") is None
    assert normalise_location(None) is None


def test_is_us_location_accepts_explicit_us_roles():
    assert is_us_location("Seattle, WA") is True
    assert is_us_location("Remote - US") is True


def test_is_us_location_rejects_foreign_remote_roles():
    assert is_us_location("Warsaw, Poland") is False
    assert is_us_location("Remote", "Based in Poland") is False
