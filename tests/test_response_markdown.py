"""Tests for converting model Markdown into the response card's rich text."""

from mystic_pointer.ui.response_markdown import render_markdown


def test_bold_and_bullets_become_rich_text() -> None:
    html = render_markdown("**Updates**\n\n* Removed the icon\n* Changed the title")

    assert "<strong>Updates</strong>" in html
    assert "<ul>" in html
    assert "<li>Removed the icon</li>" in html
    assert "**" not in html


def test_horizontal_rules_are_dropped() -> None:
    html = render_markdown("Before\n\n---\n\nAfter")

    assert "<hr" not in html
    assert "Before" in html
    assert "After" in html


def test_raw_html_cannot_inject_tags() -> None:
    html = render_markdown('<script>alert("x")</script>')

    assert "<script" not in html
    assert "&lt;script&gt;" in html


def test_tables_and_fenced_code_are_supported() -> None:
    html = render_markdown("| A | B |\n|---|---|\n| 1 | 2 |")
    assert "<table>" in html
    assert "<th>A</th>" in html
    assert "<td>1</td>" in html

    code = render_markdown("```python\nprint('hi')\n```")
    assert "<pre>" in code
    assert "print(&#x27;hi&#x27;)" in code or "print('hi')" in code


def test_blockquotes_and_headings_are_preserved() -> None:
    html = render_markdown("## Heading\n\n> quoted text")

    assert "<h2>Heading</h2>" in html
    assert "<blockquote>" in html
    assert "quoted text" in html


def test_empty_output_stays_empty() -> None:
    assert render_markdown("   \n\n") == ""
