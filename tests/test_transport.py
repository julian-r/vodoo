"""Unit tests for pure helper functions in vodoo.transport.

No Odoo instance required — only pure function logic is tested.
"""

from typing import Any

import pytest

from vodoo.transport import _build_json2_body, _parse_json2_response, _parse_name_search


# ── _build_json2_body ─────────────────────────────────────────────────────────


class TestBuildJson2Body:
    """Map execute_kw arguments into a JSON-2 request body."""

    def test_search_read_with_domain(self) -> None:
        body = _build_json2_body("search_read", [[["name", "=", "x"]]], {"fields": ["id"]})
        assert body == {"domain": [["name", "=", "x"]], "fields": ["id"]}

    def test_search_read_empty_args(self) -> None:
        body = _build_json2_body("search_read", [], None)
        assert body == {}

    def test_search_with_domain_and_kwargs(self) -> None:
        body = _build_json2_body("search", [[["active", "=", True]]], {"limit": 5})
        assert body == {"domain": [["active", "=", True]], "limit": 5}

    def test_read_with_ids_and_fields(self) -> None:
        body = _build_json2_body("read", [[1, 2], ["name"]], None)
        assert body == {"ids": [1, 2], "fields": ["name"]}

    def test_read_with_ids_only(self) -> None:
        body = _build_json2_body("read", [[1, 2]], None)
        assert body == {"ids": [1, 2]}

    def test_create_single_dict(self) -> None:
        body = _build_json2_body("create", [{"name": "x"}], None)
        assert body == {"vals_list": [{"name": "x"}]}

    def test_create_list_of_dicts(self) -> None:
        body = _build_json2_body("create", [[{"name": "a"}, {"name": "b"}]], None)
        assert body == {"vals_list": [{"name": "a"}, {"name": "b"}]}

    def test_write_with_ids_and_vals(self) -> None:
        body = _build_json2_body("write", [[1], {"name": "x"}], None)
        assert body == {"ids": [1], "vals": {"name": "x"}}

    def test_unlink_with_ids(self) -> None:
        body = _build_json2_body("unlink", [[1, 2]], None)
        assert body == {"ids": [1, 2]}

    def test_generic_method_int_list(self) -> None:
        body = _build_json2_body("action_timer_start", [[42]], None)
        assert body == {"ids": [42]}

    def test_name_search_kwargs_remapping(self) -> None:
        body = _build_json2_body(
            "name_search",
            [],
            {"name": "x", "args": [["active", "=", True]], "limit": 5},
        )
        assert "args" not in body
        assert body["domain"] == [["active", "=", True]]
        assert body["name"] == "x"
        assert body["limit"] == 5


# ── _parse_json2_response ─────────────────────────────────────────────────────


class TestParseJson2Response:
    """Parse JSON-2 response bodies."""

    def test_json_object(self) -> None:
        assert _parse_json2_response(b'{"id": 1}') == {"id": 1}

    def test_json_array(self) -> None:
        assert _parse_json2_response(b"[1, 2, 3]") == [1, 2, 3]

    def test_null(self) -> None:
        assert _parse_json2_response(b"null") is None

    def test_false(self) -> None:
        assert _parse_json2_response(b"false") is None

    def test_true(self) -> None:
        assert _parse_json2_response(b"true") is True

    def test_bare_integer(self) -> None:
        assert _parse_json2_response(b"42") == 42

    def test_bare_float(self) -> None:
        result = _parse_json2_response(b"3.14")
        assert isinstance(result, float)
        assert result == pytest.approx(3.14)

    def test_bare_string(self) -> None:
        assert _parse_json2_response(b"hello") == "hello"

    def test_whitespace_padding(self) -> None:
        assert _parse_json2_response(b"  42  ") == 42


# ── _parse_name_search ────────────────────────────────────────────────────────


class TestParseNameSearch:
    """Parse Odoo name_search results into (id, name) tuples."""

    def test_normal_result(self) -> None:
        assert _parse_name_search([[1, "Alice"], [2, "Bob"]]) == [(1, "Alice"), (2, "Bob")]

    def test_empty_list(self) -> None:
        assert _parse_name_search([]) == []

    def test_none_input(self) -> None:
        assert _parse_name_search(None) == []

    def test_string_input(self) -> None:
        assert _parse_name_search("bad") == []

    def test_malformed_entries_skipped(self) -> None:
        assert _parse_name_search([[1, "ok"], "bad", [3]]) == [(1, "ok")]

    def test_wrong_types_in_pair(self) -> None:
        assert _parse_name_search([["a", "b"]]) == []
