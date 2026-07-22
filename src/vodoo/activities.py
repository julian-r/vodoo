"""Odoo activity (``mail.activity``) operations for Vodoo."""

from __future__ import annotations

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace


class _ActivityAttrs:
    """Shared ``mail.activity`` domain attributes."""

    _model: ClassVar[str] = "mail.activity"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "res_model",
        "res_id",
        "res_name",
        "summary",
        "activity_type_id",
        "date_deadline",
        "user_id",
        "state",
        "note",
    ]
    _default_detail_fields: ClassVar[list[str] | None] = [
        *_default_fields,
        "create_date",
        "write_date",
    ]
    _record_type: ClassVar[str] = "Activity"


class ActivityNamespace(_ActivityAttrs, DomainNamespace):
    """Namespace for ``mail.activity`` operations."""

    def done(self, activity_id: int) -> Any:
        """Mark an activity as done and return Odoo's action result."""
        return self._client.execute(self._model, "action_done", [activity_id])


def build_activity_domain(
    *,
    model: str | None = None,
    user: str | None = None,
    activity_type: str | None = None,
) -> list[Any]:
    """Build a domain for activity list filtering."""
    domain: list[Any] = []
    if model:
        domain.append(("res_model", "=", model))
    if user:
        domain.append(("user_id.name", "ilike", user))
    if activity_type:
        domain.append(("activity_type_id.name", "ilike", activity_type))
    return domain


__all__ = ["ActivityNamespace", "build_activity_domain"]
