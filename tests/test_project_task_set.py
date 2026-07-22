"""Tests for ``vodoo project-task set`` output formatting."""

from __future__ import annotations

import json
from typing import Any

import click
import pytest
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo.base import configure_output
from vodoo.main import app


class _FakeTasks:
    def __init__(self) -> None:
        self.updates: list[tuple[int, dict[str, Any]]] = []

    def set(self, task_id: int, values: dict[str, Any]) -> bool:
        self.updates.append((task_id, values))
        return True


class _FakeClient:
    def __init__(self) -> None:
        self.tasks = _FakeTasks()

    def fields_get(self, model: str) -> dict[str, dict[str, str]]:
        assert model == "project.task"
        return {
            "description": {"type": "html"},
            "name": {"type": "char"},
        }


@pytest.fixture(autouse=True)
def _reset_output() -> None:
    main_module._console_config.update(simple=False, json=False, toon=False)
    configure_output(simple=False, json_mode=False, toon_mode=False)


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> _FakeClient:
    client = _FakeClient()
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    return client


def test_set_displays_html_field_as_markdown_by_default(fake_client: _FakeClient) -> None:
    result = CliRunner().invoke(
        app,
        ["project-task", "set", "42", "description=# Task Details\n\n**Important**"],
    )

    assert result.exit_code == 0
    assert "description = # Task Details" in result.output
    assert "**Important**" in result.output
    assert "<h1>" not in result.output
    assert fake_client.tasks.updates == [
        (42, {"description": "<h1>Task Details</h1>\n<p><strong>Important</strong></p>"})
    ]


def test_set_html_flag_displays_raw_html(fake_client: _FakeClient) -> None:
    result = CliRunner().invoke(
        app,
        ["project-task", "set", "42", "description=# Task Details", "--html"],
    )

    assert result.exit_code == 0
    assert "description = <h1>Task Details</h1>" in click.unstyle(result.output)
    assert fake_client.tasks.updates == [(42, {"description": "<h1>Task Details</h1>"})]


@pytest.mark.parametrize(
    ("extra_args", "expected_description"),
    [
        ([], "# Task Details"),
        (["--html"], "<h1>Task Details</h1>"),
    ],
)
def test_set_formats_structured_output(
    fake_client: _FakeClient,
    extra_args: list[str],
    expected_description: str,
) -> None:
    result = CliRunner().invoke(
        app,
        ["--json", "project-task", "set", "42", "description=# Task Details", *extra_args],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["updated"]["description"] == expected_description
    assert fake_client.tasks.updates == [(42, {"description": "<h1>Task Details</h1>"})]


def test_set_help_documents_markdown_default_and_html_opt_out() -> None:
    result = CliRunner().invoke(app, ["project-task", "set", "--help"])

    assert result.exit_code == 0
    assert "--html" in result.output
    assert "raw HTML" in result.output
    assert "markdown is the default" in result.output
