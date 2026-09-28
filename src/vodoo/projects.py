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
    """Deprecated compatibility shim for CLI stage rendering."""
    from vodoo.cli.display import display_stages as render

    render(stages)


__all__ = [
    "MILESTONE_FIELDS",
    "MILESTONE_TASK_FIELDS",
    "STAGE_FIELDS",
    "ProjectNamespace",
    "display_stages",
]
