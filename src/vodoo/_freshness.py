"""Terminal-independent, non-atomic preflight checks (never compare-and-set)."""

import re
from datetime import UTC, datetime
from typing import Any

from vodoo.exceptions import (
    RecordNotFoundError,
    RevisionInputError,
    StaleRevisionError,
    UnverifiableRevisionError,
)

_FORMAT = "%Y-%m-%d %H:%M:%S"
_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}")


def validate_write_date(value: object) -> str:
    """Require the exact UTC seconds format exposed by ordinary Odoo reads."""
    if not isinstance(value, str) or not _PATTERN.fullmatch(value):
        raise RevisionInputError("Expected write_date must use UTC YYYY-MM-DD HH:MM:SS")
    try:
        datetime.strptime(value, _FORMAT).replace(tzinfo=UTC)
    except ValueError as exc:
        raise RevisionInputError(f"Invalid expected write_date: {value!r}") from exc
    return value


def check_observations(
    model: str, ids: list[int], expected: str, records: list[dict[str, Any]]
) -> None:
    """Check fetched revisions, failing before mutation on unusable observations.

    This cannot detect changes after the read or changes within the same second.
    No mutation, RPC, retry, or expected-revision refresh occurs here.
    """
    if not ids:
        raise UnverifiableRevisionError("A freshness check requires at least one record ID")
    by_id = {record["id"]: record for record in records if "id" in record}
    for record_id in ids:
        if record_id not in by_id:
            raise RecordNotFoundError(model, record_id)
        current = by_id[record_id].get("write_date")
        try:
            current = validate_write_date(current)
        except RevisionInputError as exc:
            raise UnverifiableRevisionError(
                f"Cannot verify write_date for {model} {record_id}: {current!r}"
            ) from exc
        if current != expected:
            raise StaleRevisionError(model, record_id, expected, current)
