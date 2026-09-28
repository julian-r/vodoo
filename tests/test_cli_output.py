"""Tests for the Python library/CLI presentation boundary."""

from __future__ import annotations

import ast
import io
from collections.abc import Iterator
from pathlib import Path

import pytest
from rich.console import Console

from vodoo.cli.display import display_records
from vodoo.cli.output import (
    configure_output,
    get_renderer,
    render_error,
)
from vodoo.cli.rich import RichRenderer
from vodoo.cli.simple import SimpleRenderer
from vodoo.cli.structured import StructuredRenderer


@pytest.fixture(autouse=True)
def _restore_rich_renderer() -> Iterator[None]:
    yield
    configure_output(console=Console(file=io.StringIO()))


def test_renderer_selection() -> None:
    simple = configure_output(simple=True, stream=io.StringIO())
    assert isinstance(simple, SimpleRenderer)
    assert get_renderer() is simple

    json_renderer = configure_output(json_mode=True, stream=io.StringIO())
    assert isinstance(json_renderer, StructuredRenderer)
    assert json_renderer.mode == "json"

    toon_renderer = configure_output(toon_mode=True, stream=io.StringIO())
    assert isinstance(toon_renderer, StructuredRenderer)
    assert toon_renderer.mode == "toon"

    rich = configure_output(console=Console(file=io.StringIO()))
    assert isinstance(rich, RichRenderer)


def test_renderer_selection_rejects_conflicting_modes() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        configure_output(simple=True, json_mode=True)


def test_simple_renderer_handles_success_and_empty_results() -> None:
    stream = io.StringIO()
    configure_output(simple=True, stream=stream)

    display_records([{"id": 7, "name": "Example"}])
    display_records([])

    assert stream.getvalue() == "id\tname\n7\tExample\nNo records found\n"


def test_structured_renderer_handles_errors() -> None:
    stream = io.StringIO()
    configure_output(json_mode=True, stream=stream)

    render_error(ValueError("invalid input"), "validation", "Error")

    assert stream.getvalue() == '{"error": "invalid input", "type": "validation"}\n'


def test_core_modules_have_no_cli_imports_or_direct_output() -> None:
    package = Path(__file__).parents[1] / "src" / "vodoo"
    violations: list[str] = []

    for path in package.rglob("*.py"):
        if "cli" in path.relative_to(package).parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                forbidden = [name.name for name in node.names if name.name in {"rich", "typer"}]
                if forbidden:
                    violations.append(f"{path}: imports {', '.join(forbidden)}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".", 1)[0] in {"rich", "typer"}:
                    violations.append(f"{path}: imports {node.module}")
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
            ):
                violations.append(f"{path}:{node.lineno}: calls print()")

    assert violations == []
