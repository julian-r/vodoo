"""Async project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.aio.generated.projects import GeneratedAsyncProjectNamespace
from vodoo.generated.projects import MILESTONE_FIELDS
from vodoo.projects import _numeric_project_id, _resolved_project_name


class AsyncProjectNamespace(GeneratedAsyncProjectNamespace):
    """Async namespace for custom ``project.project`` workflows."""

    async def resolve_project_id(self, project: int | str) -> int:
        """Resolve a project ID or exact project name to an ID."""
        numeric_id = _numeric_project_id(project)
        if numeric_id is not None:
            return numeric_id

        assert isinstance(project, str)
        candidates = await self._client.search_read(
            self._model,
            domain=[("name", "=ilike", project)],
            fields=["id", "name"],
            order="id",
        )
        return _resolved_project_name(candidates, project)

    async def milestones(self, project: int | str) -> list[dict[str, Any]]:
        """List milestones for a project ID or exact project name."""
        project_id = await self.resolve_project_id(project)
        return await self._client.search_read(
            "project.milestone",
            domain=[("project_id", "=", project_id)],
            fields=MILESTONE_FIELDS,
            order="deadline, id",
        )

    async def create_milestone(self, project: int | str, name: str, deadline: str) -> int:
        """Create a milestone for a project ID or exact project name."""
        project_id = await self.resolve_project_id(project)
        return await self._client.create(
            "project.milestone",
            {"project_id": project_id, "name": name, "deadline": deadline},
        )


__all__ = ["AsyncProjectNamespace"]
