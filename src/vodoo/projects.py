"""Project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.exceptions import VodooError
from vodoo.generated.projects import (
    MILESTONE_FIELDS,
    MILESTONE_TASK_FIELDS,
    STAGE_FIELDS,
    GeneratedProjectNamespace,
)


def _numeric_project_id(project: int | str) -> int | None:
    """Return a numeric project reference without making an RPC call."""
    if isinstance(project, int) or project.isdigit():
        return int(project)
    return None


def _resolved_project_name(candidates: list[dict[str, Any]], project: str) -> int:
    """Resolve an exact case-insensitive project name from search candidates."""
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


class ProjectNamespace(GeneratedProjectNamespace):
    """Namespace for custom ``project.project`` workflows."""

    def resolve_project_id(self, project: int | str) -> int:
        """Resolve a project ID or exact project name to an ID."""
        numeric_id = _numeric_project_id(project)
        if numeric_id is not None:
            return numeric_id

        assert isinstance(project, str)
        candidates = self._client.search_read(
            self._model,
            domain=[("name", "=ilike", project)],
            fields=["id", "name"],
            order="id",
        )
        return _resolved_project_name(candidates, project)

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


__all__ = [
    "MILESTONE_FIELDS",
    "MILESTONE_TASK_FIELDS",
    "STAGE_FIELDS",
    "ProjectNamespace",
    "display_stages",
]
