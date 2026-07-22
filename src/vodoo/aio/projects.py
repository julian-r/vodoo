"""Async project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.exceptions import VodooError
from vodoo.projects import (
    MILESTONE_FIELDS,
    MILESTONE_TASK_FIELDS,
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

    async def resolve_project_id(self, project: int | str) -> int:
        """Resolve a project ID or exact project name to an ID."""
        if isinstance(project, int) or project.isdigit():
            return int(project)

        candidates = await self._client.search_read(
            self._model,
            domain=[("name", "=ilike", project)],
            fields=["id", "name"],
            order="id",
        )
        matches = [
            candidate
            for candidate in candidates
            if str(candidate.get("name", "")).casefold() == project.casefold()
        ]
        if not matches:
            raise VodooError(f"Project {project!r} not found")
        if len(matches) > 1:
            raise VodooError(f"Project name {project!r} is ambiguous; use a project ID")
        return int(matches[0]["id"])

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

    async def reach_milestone(self, milestone_id: int) -> bool:
        """Mark a milestone as reached."""
        return await self._client.write("project.milestone", [milestone_id], {"is_reached": True})

    async def milestone_tasks(self, milestone_id: int) -> list[dict[str, Any]]:
        """List tasks assigned to a milestone."""
        return await self._client.search_read(
            "project.task",
            domain=[("milestone_id", "=", milestone_id)],
            fields=MILESTONE_TASK_FIELDS,
            order="id",
        )
