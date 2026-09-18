"""Async Odoo activity (``mail.activity``) operations for Vodoo."""

from typing import Any

from vodoo.aio.generated.activities import GeneratedAsyncActivityNamespace
from vodoo.exceptions import RecordOperationError


class AsyncActivityNamespace(GeneratedAsyncActivityNamespace):
    """Async namespace for ``mail.activity`` operations."""

    async def done(self, activity_id: int) -> Any:
        """Mark an active activity as done and return Odoo's action result."""
        activity = await self.get(activity_id, fields=["active"])
        if not activity.get("active"):
            msg = f"Activity {activity_id} is already done"
            raise RecordOperationError(msg)
        return await self._client.execute(self._model, "action_done", [activity_id])


__all__ = ["AsyncActivityNamespace"]
