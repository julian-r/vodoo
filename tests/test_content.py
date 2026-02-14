"""Unit tests for vodoo.content — pure functions, no Odoo instance needed."""

import pytest

from vodoo.content import HTML, Markdown, process_values


# ── type identity ─────────────────────────────────────────────────────────────


class TestTypeIdentity:
    def test_html_is_str(self):
        assert isinstance(HTML("x"), str)

    def test_markdown_is_str(self):
        assert isinstance(Markdown("x"), str)

    def test_html_is_html(self):
        assert isinstance(HTML("x"), HTML)

    def test_markdown_is_markdown(self):
        assert isinstance(Markdown("x"), Markdown)


# ── process_values ────────────────────────────────────────────────────────────


class TestProcessValues:
    def test_plain_string_unchanged(self):
        result = process_values({"name": "hello"})
        assert result == {"name": "hello"}
        assert type(result["name"]) is str

    def test_html_unwrapped_to_plain_str(self):
        result = process_values({"desc": HTML("<b>hi</b>")})
        assert result == {"desc": "<b>hi</b>"}
        assert type(result["desc"]) is str
        assert not isinstance(result["desc"], HTML)

    def test_markdown_converted_to_html(self):
        result = process_values({"desc": Markdown("# Title")})
        assert "<h1>" in result["desc"]
        assert "Title" in result["desc"]
        assert type(result["desc"]) is str
        assert not isinstance(result["desc"], Markdown)

    def test_non_string_values_pass_through(self):
        values = {"count": 42, "active": True, "ratio": 3.14, "empty": None}
        assert process_values(values) == values

    def test_mixed_values(self):
        values = {
            "name": "plain",
            "body": HTML("<p>raw</p>"),
            "notes": Markdown("**bold**"),
            "count": 7,
        }
        result = process_values(values)
        assert result["name"] == "plain"
        assert result["body"] == "<p>raw</p>"
        assert not isinstance(result["body"], HTML)
        assert "<strong>" in result["notes"] or "<b>" in result["notes"]
        assert result["count"] == 7

    def test_empty_dict(self):
        assert process_values({}) == {}
