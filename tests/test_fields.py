"""Unit tests for pure field-parsing helpers in :mod:`vodoo.fields`.

No Odoo instance required — only pure function logic is exercised.
"""

from __future__ import annotations

import pytest

from vodoo.exceptions import FieldParsingError
from vodoo.fields import _apply_operator, _match_field_assignment, _parse_raw_value


# ── _match_field_assignment ──────────────────────────────────────────────────


class TestMatchFieldAssignment:
    """Regex-based field=value parsing."""

    def test_simple_assignment(self) -> None:
        assert _match_field_assignment("name=value") == ("name", "=", "value")

    def test_plus_equals(self) -> None:
        assert _match_field_assignment("field+=5") == ("field", "+=", "5")

    def test_minus_equals(self) -> None:
        assert _match_field_assignment("field-=3") == ("field", "-=", "3")

    def test_multiply_equals(self) -> None:
        assert _match_field_assignment("field*=2") == ("field", "*=", "2")

    def test_divide_equals(self) -> None:
        assert _match_field_assignment("field/=4") == ("field", "/=", "4")

    def test_value_with_spaces(self) -> None:
        assert _match_field_assignment("name=hello world") == ("name", "=", "hello world")

    def test_value_with_equals_sign(self) -> None:
        field, op, val = _match_field_assignment("field=a=b")
        assert (field, op) == ("field", "=")
        assert val == "a=b"

    def test_multiline_value(self) -> None:
        field, op, val = _match_field_assignment("field=line1\nline2")
        assert (field, op) == ("field", "=")
        assert val == "line1\nline2"

    def test_invalid_format_no_equals(self) -> None:
        with pytest.raises(FieldParsingError):
            _match_field_assignment("no-equals-sign")

    def test_empty_value_raises(self) -> None:
        # Regex requires .+ for value, so empty value is invalid
        with pytest.raises(FieldParsingError):
            _match_field_assignment("field=")

    def test_whitespace_stripped_from_field(self) -> None:
        field, op, val = _match_field_assignment("  name  =value")
        assert field == "name"


# ── _parse_raw_value ─────────────────────────────────────────────────────────


class TestParseRawValue:
    """Type coercion of raw CLI string values."""

    def test_integer(self) -> None:
        assert _parse_raw_value("f", "42") == 42
        assert isinstance(_parse_raw_value("f", "42"), int)

    def test_negative_integer(self) -> None:
        assert _parse_raw_value("f", "-7") == -7
        assert isinstance(_parse_raw_value("f", "-7"), int)

    def test_float(self) -> None:
        assert _parse_raw_value("f", "3.14") == pytest.approx(3.14)
        assert isinstance(_parse_raw_value("f", "3.14"), float)

    def test_boolean_true_variants(self) -> None:
        for val in ("true", "True", "TRUE"):
            assert _parse_raw_value("f", val) is True

    def test_boolean_false(self) -> None:
        assert _parse_raw_value("f", "false") is False

    def test_json_list(self) -> None:
        assert _parse_raw_value("f", "json:[1,2,3]") == [1, 2, 3]

    def test_json_object(self) -> None:
        assert _parse_raw_value("f", 'json:{"a": 1}') == {"a": 1}

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(FieldParsingError):
            _parse_raw_value("f", "json:{bad")

    def test_double_quoted_string(self) -> None:
        assert _parse_raw_value("f", '"hello"') == "hello"

    def test_single_quoted_string(self) -> None:
        assert _parse_raw_value("f", "'hello'") == "hello"

    def test_plain_string_unchanged(self) -> None:
        assert _parse_raw_value("f", "hello") == "hello"


# ── _apply_operator ──────────────────────────────────────────────────────────


class TestApplyOperator:
    """Compound assignment arithmetic."""

    def test_plus_equals(self) -> None:
        assert _apply_operator("f", "+=", 3, 10) == 13

    def test_minus_equals(self) -> None:
        assert _apply_operator("f", "-=", 3, 10) == 7

    def test_multiply_equals(self) -> None:
        assert _apply_operator("f", "*=", 3, 10) == 30

    def test_divide_equals_int_result(self) -> None:
        result = _apply_operator("f", "/=", 2, 10)
        assert result == 5
        assert isinstance(result, int)

    def test_divide_equals_float_result(self) -> None:
        result = _apply_operator("f", "/=", 3, 10)
        assert result == pytest.approx(10 / 3)
        assert isinstance(result, float)

    def test_divide_by_zero_raises(self) -> None:
        with pytest.raises(FieldParsingError, match="Division by zero"):
            _apply_operator("f", "/=", 0, 10)

    def test_non_numeric_current_value_raises(self) -> None:
        with pytest.raises(FieldParsingError, match="non-numeric"):
            _apply_operator("f", "+=", 3, "ten")

    def test_none_current_value_raises(self) -> None:
        with pytest.raises(FieldParsingError, match="None"):
            _apply_operator("f", "+=", 3, None)

    def test_non_numeric_parsed_value_raises(self) -> None:
        with pytest.raises(FieldParsingError, match="requires numeric"):
            _apply_operator("f", "+=", "three", 10)
