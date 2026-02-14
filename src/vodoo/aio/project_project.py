"""Async project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.project_project import (
    STAGE_FIELDS,
    ProjectNamespace,
)
from vodoo.project_project import (
    display_project_detail as display_project_detail,
)
from vodoo.project_project import (
    display_projects as display_projects,
)
from vodoo.project_project import (
    display_stages as display_stages,
)


class AsyncProjectNamespace(AsyncDomainNamespace):
    """Async namespace for project.project operations."""

    _model = ProjectNamespace._model
    _default_fields = ProjectNamespace._default_fields
    _default_detail_fields = ProjectNamespace._default_detail_fields
    _record_type = ProjectNamespace._record_type

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
