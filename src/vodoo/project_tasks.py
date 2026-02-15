"""Project task operations for Vodoo."""

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.content import Markdown


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


class TaskNamespace(DomainNamespace):
    """Project task namespace."""

    _model = "project.task"
    _tag_model = "project.tags"
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
        return self._client.create(self._tag_model, values)

    def delete_tag(self, tag_id: int) -> bool:
        """Delete a project tag.

        Args:
            tag_id: Tag ID

        Returns:
            True if successful
        """
        return self._client.unlink(self._tag_model, [tag_id])
