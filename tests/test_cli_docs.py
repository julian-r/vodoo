"""Tests for generated CLI reference documentation."""

from __future__ import annotations

import click
import typer.main

from scripts.gen_cli_docs import format_type, generate_command_doc
from vodoo.main import app


def test_variadic_argument_type_uses_ellipsis() -> None:
    argument = click.Argument(["blocked_by_ids"], type=int, nargs=-1, required=True)

    assert format_type(argument) == "INT..."


def test_generate_command_doc_marks_required_options_without_duplication() -> None:
    command = click.Command(
        "example",
        params=[
            click.Option(["--value"], required=True, default=None, help="Required value"),
            click.Option(["--other"], required=True, default=None, help="Other value"),
        ],
    )

    rendered = generate_command_doc(command, "example")

    assert "| `--value` | TEXT | Required value |" in rendered
    assert "| `--other` | TEXT | Other value (required) |" in rendered
    assert "Required value (required)" not in rendered


def test_generate_command_doc_renders_nested_subcommands() -> None:
    root = typer.main.get_command(app)
    assert isinstance(root, click.Group)
    root_context = click.Context(root)
    project_task = root.get_command(root_context, "project-task")
    assert isinstance(project_task, click.Group)
    project_task_context = click.Context(project_task, parent=root_context)
    depends = project_task.get_command(project_task_context, "depends")
    assert isinstance(depends, click.Group)

    rendered = generate_command_doc(depends, "depends")

    assert "### depends" in rendered
    assert "#### depends add" in rendered
    assert "#### depends clear" in rendered
    assert "| `blocked_by_ids` | INT... | IDs of tasks that must be completed first |" in rendered
