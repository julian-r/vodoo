"""Async project task operations for Vodoo."""

from typing import Any, ClassVar

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.project import (
    TaskNamespace,
    _build_task_values,
    display_task_detail,
    display_task_tags,
    display_tasks,
)


class AsyncTaskNamespace(AsyncDomainNamespace):
    """Async project task namespace."""

    _model = TaskNamespace._model
    _tag_model = TaskNamespace._tag_model
    _default_fields: ClassVar[list[str]] = list(TaskNamespace._default_fields)
    _record_type = TaskNamespace._record_type

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

    async def create_tag(self, name: str, color: int | None = None) -> int:
        """Create a new project tag."""
        values: dict[str, Any] = {"name": name}
        if color is not None:
            values["color"] = color
        return await self._client.create(self._tag_model, values)

    async def delete_tag(self, tag_id: int) -> bool:
        """Delete a project tag."""
        return await self._client.unlink(self._tag_model, [tag_id])


__all__ = [
    "AsyncTaskNamespace",
    "display_task_detail",
    "display_task_tags",
    "display_tasks",
]
