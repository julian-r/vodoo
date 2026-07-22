"""Async Odoo activity (``mail.activity``) operations for Vodoo."""

from typing import Any

from vodoo.activities import _ActivityAttrs
from vodoo.aio._domain import AsyncDomainNamespace


class AsyncActivityNamespace(_ActivityAttrs, AsyncDomainNamespace):
    """Async namespace for ``mail.activity`` operations."""

    async def done(self, activity_id: int) -> Any:
        """Mark an activity as done and return Odoo's action result."""
        return await self._client.execute(self._model, "action_done", [activity_id])


__all__ = ["AsyncActivityNamespace"]
