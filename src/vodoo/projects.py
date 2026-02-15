"""Project (project.project) operations for Vodoo."""

from __future__ import annotations

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace

# Fields for stage listing
STAGE_FIELDS = ["id", "name", "sequence", "fold", "project_ids"]


class ProjectNamespace(DomainNamespace):
    """Namespace for project.project operations."""

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
    _default_detail_fields: ClassVar[list[str]] = [
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


def display_projects(projects: list[dict[str, Any]]) -> None:
    """Display projects in a rich table.

    Args:
        projects: List of project dictionaries

    """
    from vodoo.base import display_records

    display_records(projects, title="Projects")


def display_project_detail(project: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed project information.

    Args:
        project: Project dictionary
        show_html: If True, show raw HTML description, else convert to markdown

    """
    from vodoo.base import display_record_detail

    display_record_detail(project, show_html=show_html, record_type="Project")


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
