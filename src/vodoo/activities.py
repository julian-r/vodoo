"""Odoo activity (``mail.activity``) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.exceptions import RecordOperationError
from vodoo.generated.activities import GeneratedActivityNamespace


class ActivityNamespace(GeneratedActivityNamespace):
    """Namespace for ``mail.activity`` operations."""

    def done(self, activity_id: int) -> Any:
        """Mark an active activity as done and return Odoo's action result."""
        activity = self.get(activity_id, fields=["active"])
        if not activity.get("active"):
            msg = f"Activity {activity_id} is already done"
            raise RecordOperationError(msg)
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
