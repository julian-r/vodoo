"""Async project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.projects import (
    STAGE_FIELDS,
    _ProjectAttrs,
)


class AsyncProjectNamespace(_ProjectAttrs, AsyncDomainNamespace):
    """Async namespace for project.project operations."""

    async def stages(self, project_id: int | None = None) -> list[dict[str, Any]]:
        """List task stages, optionally filtered by project.

        Args:
            project_id: Project ID to filter stages (None = all stages)

        Returns:
            List of stage dictionaries with id, name, sequence, fold

        """
        domain: list[Any] = []
        if project_id is not None:
            domain.append(("project_ids", "in", [project_id]))

        return await self._client.search_read(
            "project.task.type",
            domain=domain,
            fields=STAGE_FIELDS,
            order="sequence",
        )
