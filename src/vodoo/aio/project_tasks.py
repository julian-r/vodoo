"""Async project task operations for Vodoo."""

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.cmd import Cmd
from vodoo.exceptions import RecordNotFoundError, RecordOperationError
from vodoo.project_tasks import (
    _build_task_values,
    _project_id,
    _TaskAttrs,
    _validate_schedule_values,
)


class AsyncTaskNamespace(_TaskAttrs, AsyncDomainNamespace):
    """Async project task namespace."""

    async def create(
        self,
        name: str,
        project_id: int,
        description: str | None = None,
        user_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        parent_id: int | None = None,
        **kwargs: Any,
    ) -> int:
        """Create a new project task."""
        values, context = _build_task_values(
            name, project_id, description, user_ids, tag_ids, parent_id, **kwargs
        )
        return await self._client.create(self._model, values, context=context)

    async def set_milestone(self, task_id: int, milestone_id: int) -> bool:
        """Assign a task to a milestone in the same project."""
        tasks = await self._client.read(self._model, [task_id], fields=["project_id"])
        if not tasks:
            raise RecordNotFoundError(self._model, task_id)

        milestones = await self._client.read(
            "project.milestone", [milestone_id], fields=["project_id"]
        )
        if not milestones:
            raise RecordNotFoundError("project.milestone", milestone_id)

        task_project_id = _project_id(tasks[0])
        milestone_project_id = _project_id(milestones[0])
        if task_project_id is None or milestone_project_id is None:
            raise RecordOperationError("Task and milestone must both belong to a project")
        if task_project_id != milestone_project_id:
            raise RecordOperationError(
                f"Task {task_id} and milestone {milestone_id} belong to different projects"
            )

        return await self._client.write(self._model, [task_id], {"milestone_id": milestone_id})

    async def add_dependencies(self, task_id: int, dependency_ids: list[int]) -> bool:
        """Add tasks that must be completed before this task."""
        commands = [Cmd.link(dependency_id) for dependency_id in dependency_ids]
        return await self.set(task_id, {"depend_on_ids": commands})

    async def clear_dependencies(self, task_id: int) -> bool:
        """Remove all dependencies from a task."""
        return await self.set(task_id, {"depend_on_ids": [Cmd.clear()]})

    async def schedule(self, task_id: int, start: str, end: str) -> bool:
        """Set Gantt scheduling dates (requires Odoo Project Enterprise).

        Args:
            task_id: Task ID.
            start: Planned start datetime in ``YYYY-MM-DD HH:MM:SS`` format.
            end: Deadline in ``YYYY-MM-DD`` format.

        Returns:
            True if successful.
        """
        _validate_schedule_values(start, end)
        return await self.set(
            task_id,
            {"planned_date_begin": start, "date_deadline": end},
        )

    async def create_tag(self, name: str, color: int | None = None) -> int:
        """Create a new project tag."""
        values: dict[str, Any] = {"name": name}
        if color is not None:
            values["color"] = color
        assert self._tag_model is not None
        return await self._client.create(self._tag_model, values)

    async def delete_tag(self, tag_id: int) -> bool:
        """Delete a project tag."""
        assert self._tag_model is not None
        return await self._client.unlink(self._tag_model, [tag_id])


__all__ = ["AsyncTaskNamespace"]
