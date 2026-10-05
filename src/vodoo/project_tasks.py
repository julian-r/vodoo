"""Project task operations for Vodoo."""

from datetime import datetime
from typing import Any

from vodoo.cmd import Cmd
from vodoo.content import HTML, Markdown
from vodoo.exceptions import RecordNotFoundError, RecordOperationError
from vodoo.generated.project_tasks import GeneratedTaskNamespace
from vodoo.task_context import get_task_context

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


def _validate_task_relation_ids(
    project_id: int,
    user_ids: list[int] | None = None,
    tag_ids: list[int] | None = None,
    parent_id: int | None = None,
    *,
    stage_id: int | None = None,
    depend_on_ids: list[int] | None = None,
) -> None:
    """Reject invalid relation IDs locally, before any task creation request."""
    relations = {
        "project_id": [project_id],
        "parent_id": [] if parent_id is None else [parent_id],
        "stage_id": [] if stage_id is None else [stage_id],
        "user_ids": [] if user_ids is None else user_ids,
        "tag_ids": [] if tag_ids is None else tag_ids,
        "depend_on_ids": [] if depend_on_ids is None else depend_on_ids,
    }
    for field, ids in relations.items():
        for record_id in ids:
            if isinstance(record_id, bool) or not isinstance(record_id, int) or record_id <= 0:
                raise ValueError(f"{field} must contain only positive integer IDs")


def _build_task_values(
    name: str,
    project_id: int,
    description: str | None = None,
    user_ids: list[int] | None = None,
    tag_ids: list[int] | None = None,
    parent_id: int | None = None,
    *,
    stage_id: int | None = None,
    depend_on_ids: list[int] | None = None,
    **kwargs: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build values and context dicts for task creation.

    Returns:
        Tuple of (values, context) dictionaries
    """
    _validate_task_relation_ids(
        project_id, user_ids, tag_ids, parent_id, stage_id=stage_id, depend_on_ids=depend_on_ids
    )
    values: dict[str, Any] = {
        **kwargs,
        "name": name,
        "project_id": project_id,
    }

    if description is not None:
        values["description"] = (
            description if isinstance(description, HTML) else Markdown(description)
        )
    for field, ids in (
        ("user_ids", user_ids),
        ("tag_ids", tag_ids),
        ("depend_on_ids", depend_on_ids),
    ):
        if ids is not None:
            values[field] = [Cmd.set(ids)]
    if parent_id is not None:
        values["parent_id"] = parent_id
    if stage_id is not None:
        values["stage_id"] = stage_id

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


class TaskNamespace(GeneratedTaskNamespace):
    """Project task namespace."""

    def context(
        self,
        task_id: int,
        fields: list[str] | None = None,
        *,
        page_size: int = 100,
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        """Read task fields, resolved relations, chatter, attachments and URL.

        See ``spec/v1/task-context.schema.json`` for the stable response contract.
        Reads are not an atomic snapshot. Check ``complete``, ``errors`` and
        ``pagination`` before acting on the returned information.
        """
        return get_task_context(
            self._client, task_id, fields, page_size=page_size, max_pages=max_pages
        )

    def create(
        self,
        name: str,
        project_id: int,
        description: str | None = None,
        user_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        parent_id: int | None = None,
        *,
        stage_id: int | None = None,
        depend_on_ids: list[int] | None = None,
        **kwargs: Any,
    ) -> int:
        """Create a new project task.

        Args:
            name: Task name
            project_id: Project ID (required)
            description: Markdown task description; wrap in HTML to bypass conversion
            user_ids: List of assigned user IDs
            tag_ids: List of tag IDs
            parent_id: Parent task ID (for subtasks)
            stage_id: Stage ID
            depend_on_ids: IDs of tasks that must be completed first
            **kwargs: Additional field values

        All relation IDs must be positive integers. All supplied fields are sent
        in one create request; no placeholder task or follow-up writes are used.

        Returns:
            ID of created task
        """
        values, context = _build_task_values(
            name,
            project_id,
            description,
            user_ids,
            tag_ids,
            parent_id,
            stage_id=stage_id,
            depend_on_ids=depend_on_ids,
            **kwargs,
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
