"""Field assignment parsing for CLI ``field=value`` syntax.

Extracted from :mod:`vodoo.base` to keep that module focused on CRUD and
display concerns.  The three helpers (``_match_field_assignment``,
``_parse_raw_value``, ``_apply_operator``) are pure functions with no I/O —
only ``parse_field_assignment`` touches the network (to fetch field metadata
and current values for compound operators).
"""

from __future__ import annotations

import contextlib
import json
import re
from typing import TYPE_CHECKING, Any

from vodoo.exceptions import FieldParsingError

if TYPE_CHECKING:
    from vodoo.client import OdooClient


def _match_field_assignment(field_assignment: str) -> tuple[str, str, str]:
    """Match a field assignment string and return (field, operator, value).

    Raises:
        FieldParsingError: If the assignment format is invalid.
    """
    match = re.match(r"^([^=+\-*/]+)([\+\-*/]?=)(.+)$", field_assignment, re.DOTALL)
    if not match:
        msg = f"Invalid format '{field_assignment}'. Use field=value or field+=value"
        raise FieldParsingError(msg)
    field = match.group(1).strip()
    operator = match.group(2).strip()
    value = match.group(3).strip()
    return field, operator, value


def _parse_raw_value(field: str, value: str) -> Any:
    """Parse a raw string value into a typed Python value.

    Handles ``json:`` prefix, integers, floats, booleans, and quoted strings.
    """
    parsed_value: Any = value
    if value.startswith("json:"):
        try:
            parsed_value = json.loads(value[5:])
        except json.JSONDecodeError as e:
            msg = f"Invalid JSON for field '{field}': {e}"
            raise FieldParsingError(msg) from e
    elif value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
        parsed_value = int(value)
    elif value.replace(".", "", 1).replace("-", "", 1).isdigit():
        with contextlib.suppress(ValueError):
            parsed_value = float(value)
    elif value.lower() in ("true", "false"):
        parsed_value = value.lower() == "true"
    elif (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        parsed_value = value[1:-1]
    return parsed_value


def _apply_operator(field: str, operator: str, parsed_value: Any, current_value: Any) -> Any:
    """Apply a compound operator (``+=``, ``-=``, ``*=``, ``/=``).

    Raises:
        FieldParsingError: On non-numeric values or division by zero.
    """
    if current_value is None:
        msg = f"Field '{field}' not found or is None"
        raise FieldParsingError(msg)

    if not isinstance(current_value, (int, float)):
        msg = f"Field '{field}' has non-numeric value: {current_value}"
        raise FieldParsingError(msg)

    if not isinstance(parsed_value, (int, float)):
        msg = f"Operator '{operator}' requires numeric value, got: {parsed_value}"
        raise FieldParsingError(msg)

    if operator == "+=":
        return current_value + parsed_value
    if operator == "-=":
        return current_value - parsed_value
    if operator == "*=":
        return current_value * parsed_value
    # operator == "/="
    if parsed_value == 0:
        msg = "Division by zero"
        raise FieldParsingError(msg)
    result = current_value / parsed_value
    if isinstance(current_value, int) and isinstance(parsed_value, int) and result == int(result):
        return int(result)
    return result


def parse_field_assignment(
    client: OdooClient,
    model: str,
    record_id: int,
    field_assignment: str,
    no_markdown: bool = False,
) -> tuple[str, Any]:
    """Parse a field assignment and return field name and computed value.

    HTML fields automatically get markdown conversion unless no_markdown=True.

    Args:
        client: Odoo client
        model: Model name
        record_id: Record ID
        field_assignment: Field assignment string (e.g., 'field=value', 'field+=5')
        no_markdown: If True, disable automatic markdown conversion for HTML fields

    Returns:
        Tuple of (field_name, value)

    Raises:
        FieldParsingError: If assignment format is invalid

    Examples:
        >>> parse_field_assignment(client, "project.task", 42, "name=New Title")
        ('name', 'New Title')
        >>> parse_field_assignment(client, "project.task", 42, "priority+=1")
        ('priority', 3)  # if current priority is 2

    """
    from vodoo.base import _convert_to_html, get_record, list_fields

    field, operator, value = _match_field_assignment(field_assignment)
    parsed_value = _parse_raw_value(field, value)
    # Auto-convert markdown to HTML for HTML fields
    if isinstance(parsed_value, str) and not no_markdown:
        fields_info = list_fields(client, model)
        if field in fields_info and fields_info[field].get("type") == "html":
            parsed_value = _convert_to_html(parsed_value, use_markdown=True)
    if operator in ("+=", "-=", "*=", "/="):
        record = get_record(client, model, record_id, fields=[field])
        current_value = record.get(field)
        parsed_value = _apply_operator(field, operator, parsed_value, current_value)

    return field, parsed_value
