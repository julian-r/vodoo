"""Project task operations for Vodoo."""

from datetime import datetime
from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.cmd import Cmd
from vodoo.content import Markdown
from vodoo.exceptions import RecordNotFoundError, RecordOperationError

_START_FORMAT = "%Y-%m-%d %H:%M:%S"
_END_FORMAT = "%Y-%m-%d"


def _validate_schedule_values(start: str, end: str) -> None:
    """Validate task schedule values against Odoo's documented formats."""
    try:
        parsed_start = datetime.strptime(start, _START_FORMAT)  # noqa: DTZ007
    except ValueError as exc:
        msg = "start must use YYYY-MM-DD HH:MM:SS format"
        raise ValueError(msg) from exc
    if parsed_start.strftime(_START_FORMAT) != start:
        msg = "start must use YYYY-MM-DD HH:MM:SS format"
        raise ValueError(msg)

    try:
        parsed_end = datetime.strptime(end, _END_FORMAT)  # noqa: DTZ007
    except ValueError as exc:
        msg = "end must use YYYY-MM-DD format"
        raise ValueError(msg) from exc
    if parsed_end.strftime(_END_FORMAT) != end:
        msg = "end must use YYYY-MM-DD format"
        raise ValueError(msg)


def _build_task_values(
    name: str,
    project_id: int,
    description: str | None = None,
    user_ids: list[int] | None = None,
    tag_ids: list[int] | None = None,
    parent_id: int | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build values and context dicts for task creation.

    Returns:
        Tuple of (values, context) dictionaries
    """
    values: dict[str, Any] = {
        "name": name,
        "project_id": project_id,
    }

    if description:
        values["description"] = Markdown(description)
    if user_ids:
        values["user_ids"] = [(6, 0, user_ids)]
    if tag_ids:
        values["tag_ids"] = [(6, 0, tag_ids)]
    if parent_id:
        values["parent_id"] = parent_id

    values.update(kwargs)

    context: dict[str, Any] = {"default_project_id": project_id}
    return values, context


def _project_id(record: dict[str, Any]) -> int | None:
    """Extract a project ID from an Odoo many2one value."""
    value = record.get("project_id")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, (list, tuple)) and value:
        return int(value[0])
    return None


class _TaskAttrs:
    """Shared domain attributes for task namespaces."""

    _model = "project.task"
    _tag_model: str | None = "project.tags"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "partner_id",
        "project_id",
        "stage_id",
        "user_ids",
        "priority",
        "tag_ids",
        "create_date",
    ]
    _record_type = "Task"


class TaskNamespace(_TaskAttrs, DomainNamespace):
    """Project task namespace."""

    def create(
        self,
        name: str,
        project_id: int,
        description: str | None = None,
        user_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        parent_id: int | None = None,
        **kwargs: Any,
    ) -> int:
        """Create a new project task.

        Args:
            name: Task name
            project_id: Project ID (required)
            description: Task description (HTML)
            user_ids: List of assigned user IDs
            tag_ids: List of tag IDs
            parent_id: Parent task ID (for subtasks)
            **kwargs: Additional field values

        Returns:
            ID of created task
        """
        values, context = _build_task_values(
            name, project_id, description, user_ids, tag_ids, parent_id, **kwargs
        )
        return self._client.create(self._model, values, context=context)

    def set_milestone(self, task_id: int, milestone_id: int) -> bool:
        """Assign a task to a milestone in the same project."""
        tasks = self._client.read(self._model, [task_id], fields=["project_id"])
        if not tasks:
            raise RecordNotFoundError(self._model, task_id)

        milestones = self._client.read("project.milestone", [milestone_id], fields=["project_id"])
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

        return self._client.write(self._model, [task_id], {"milestone_id": milestone_id})

    def add_dependencies(self, task_id: int, dependency_ids: list[int]) -> bool:
        """Add tasks that must be completed before this task.

        Existing dependencies are preserved.

        Args:
            task_id: ID of the blocked task.
            dependency_ids: IDs of the tasks blocking it.

        Returns:
            True if successful.
        """
        commands = [Cmd.link(dependency_id) for dependency_id in dependency_ids]
        return self.set(task_id, {"depend_on_ids": commands})

    def clear_dependencies(self, task_id: int) -> bool:
        """Remove all dependencies from a task.

        Args:
            task_id: Task ID.

        Returns:
            True if successful.
        """
        return self.set(task_id, {"depend_on_ids": [Cmd.clear()]})

    def schedule(self, task_id: int, start: str, end: str) -> bool:
        """Set Gantt scheduling dates (requires Odoo Project Enterprise).

        Args:
            task_id: Task ID.
            start: Planned start datetime in ``YYYY-MM-DD HH:MM:SS`` format.
            end: Deadline in ``YYYY-MM-DD`` format.

        Returns:
            True if successful.
        """
        _validate_schedule_values(start, end)
        return self.set(
            task_id,
            {"planned_date_begin": start, "date_deadline": end},
        )

    def create_tag(self, name: str, color: int | None = None) -> int:
        """Create a new project tag.

        Args:
            name: Tag name
            color: Tag color index (0-11, optional)

        Returns:
            ID of created tag
        """
        values: dict[str, Any] = {"name": name}
        if color is not None:
            values["color"] = color
        assert self._tag_model is not None
        return self._client.create(self._tag_model, values)

    def delete_tag(self, tag_id: int) -> bool:
        """Delete a project tag.

        Args:
            tag_id: Tag ID

        Returns:
            True if successful
        """
        assert self._tag_model is not None
        return self._client.unlink(self._tag_model, [tag_id])
