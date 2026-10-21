from jobtracker.normalize.html import html_to_text, truncate_text


def test_strips_tags():
    assert html_to_text("<p>Hello <b>world</b></p>") == "Hello world"


def test_removes_script():
    html = "<p>Text</p><script>alert(1)</script>"
    result = html_to_text(html)
    assert "alert" not in result
    assert "Text" in result


def test_removes_style():
    html = "<style>body{color:red}</style><p>Content</p>"
    assert "color" not in html_to_text(html)
    assert "Content" in html_to_text(html)


def test_empty_input():
    assert html_to_text(None) == ""
    assert html_to_text("") == ""


def test_plain_text_unchanged():
    assert html_to_text("plain text") == "plain text"


def test_truncate_at_word_boundary():
    text = "hello world foo bar"
    result = truncate_text(text, max_chars=11)
    assert result == "hello world"
    assert len(result) <= 11


def test_truncate_no_op_when_short():
    text = "short"
    assert truncate_text(text, max_chars=100) == "short"
