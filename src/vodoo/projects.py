"""Project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace

# Fields for stage listing
STAGE_FIELDS = ["id", "name", "sequence", "fold", "project_ids"]


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


def display_stages(stages: list[dict[str, Any]]) -> None:
    """Display stages in a table or TSV format.

    Args:
        stages: List of stage dictionaries

    """
    from vodoo.base import _is_simple_output

    if _is_simple_output():
        print("id\tname\tsequence\tfold")
        for stage in stages:
            fold = "true" if stage.get("fold") else "false"
            print(f"{stage['id']}\t{stage['name']}\t{stage.get('sequence', '')}\t{fold}")
    else:
        from rich.console import Console
        from rich.table import Table

        console = Console()
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
