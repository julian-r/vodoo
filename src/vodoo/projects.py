"""Project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.exceptions import VodooError

# Fields for stage and milestone listing
STAGE_FIELDS = ["id", "name", "sequence", "fold", "project_ids"]
MILESTONE_FIELDS = [
    "id",
    "name",
    "project_id",
    "deadline",
    "is_reached",
    "reached_date",
    "is_deadline_exceeded",
]
MILESTONE_TASK_FIELDS = [
    "id",
    "name",
    "project_id",
    "milestone_id",
    "stage_id",
    "user_ids",
    "priority",
]


class _ProjectAttrs:
    """Shared domain attributes for project.project."""

    _model = "project.project"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "user_id",
        "partner_id",
        "date_start",
        "date",
        "task_count",
        "color",
    ]
    _default_detail_fields: ClassVar[list[str] | None] = [
        "id",
        "name",
        "description",
        "active",
        "user_id",
        "partner_id",
        "company_id",
        "date_start",
        "date",
        "task_count",
        "tag_ids",
        "color",
        "write_date",
    ]
    _record_type = "Project"


class ProjectNamespace(_ProjectAttrs, DomainNamespace):
    """Namespace for project.project operations."""

    def stages(self, project_id: int | None = None) -> list[dict[str, Any]]:
        """List task stages, optionally filtered by project.

        Args:
            project_id: Project ID to filter stages (None = all stages)

        Returns:
            List of stage dictionaries with id, name, sequence, fold

        """
        domain: list[Any] = []
        if project_id is not None:
            domain.append(("project_ids", "in", [project_id]))

        return self._client.search_read(
            "project.task.type",
            domain=domain,
            fields=STAGE_FIELDS,
            order="sequence",
        )

    def resolve_project_id(self, project: int | str) -> int:
        """Resolve a project ID or exact project name to an ID."""
        if isinstance(project, int) or project.isdigit():
            return int(project)

        candidates = self._client.search_read(
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

    def milestones(self, project: int | str) -> list[dict[str, Any]]:
        """List milestones for a project ID or exact project name."""
        project_id = self.resolve_project_id(project)
        return self._client.search_read(
            "project.milestone",
            domain=[("project_id", "=", project_id)],
            fields=MILESTONE_FIELDS,
            order="deadline, id",
        )

    def create_milestone(self, project: int | str, name: str, deadline: str) -> int:
        """Create a milestone for a project ID or exact project name."""
        project_id = self.resolve_project_id(project)
        return self._client.create(
            "project.milestone",
            {"project_id": project_id, "name": name, "deadline": deadline},
        )

    def reach_milestone(self, milestone_id: int) -> bool:
        """Mark a milestone as reached."""
        return self._client.write("project.milestone", [milestone_id], {"is_reached": True})

    def milestone_tasks(self, milestone_id: int) -> list[dict[str, Any]]:
        """List tasks assigned to a milestone."""
        return self._client.search_read(
            "project.task",
            domain=[("milestone_id", "=", milestone_id)],
            fields=MILESTONE_TASK_FIELDS,
            order="id",
        )


def display_stages(stages: list[dict[str, Any]]) -> None:
    """Display stages in a table, TSV, or JSON format.

    Args:
        stages: List of stage dictionaries

    """
    from vodoo.base import _get_console, _is_simple_output, is_structured_output, structured_print

    if is_structured_output():
        structured_print(stages)
        return

    if _is_simple_output():
        print("id\tname\tsequence\tfold")
        for stage in stages:
            fold = "true" if stage.get("fold") else "false"
            print(f"{stage['id']}\t{stage['name']}\t{stage.get('sequence', '')}\t{fold}")
    else:
        from rich.table import Table

        console = _get_console()
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("ID", style="cyan", justify="right")
        table.add_column("Name", style="green")
        table.add_column("Sequence", justify="right")
        table.add_column("Folded", justify="center")

        for stage in stages:
            table.add_row(
                str(stage["id"]),
                stage["name"],
                str(stage.get("sequence", "")),
                "✓" if stage.get("fold") else "",
            )

        console.print(table)
