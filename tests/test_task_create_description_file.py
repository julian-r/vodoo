"""Integrated create workflow with shared UTF-8 description input."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from tests.test_project_task_create import _config, _transport
from vodoo import main
from vodoo.cli.output import configure_output
from vodoo.client import OdooClient


@pytest.fixture(autouse=True)
def _reset_output() -> Iterator[None]:
    main._console_config.update(simple=False, json=False, toon=False)
    configure_output()
    yield
    main._console_config.update(simple=False, json=False, toon=False)
    configure_output()


@pytest.mark.parametrize("stdin", [False, True])
@pytest.mark.parametrize("no_markdown", [False, True])
def test_create_file_and_stdin_are_one_mutation(
    tmp_path: Path, stdin: bool, no_markdown: bool
) -> None:
    content = "# Grüße\n\n**Résumé**\n"
    path = tmp_path / "task.md"
    path.write_text(content, encoding="utf-8")
    transport = _transport()
    args = [
        "--json",
        "project-task",
        "create",
        "--name",
        "Task",
        "--project",
        "2",
        "--description-file",
        "-" if stdin else str(path),
    ]
    if no_markdown:
        args.append("--no-markdown")
    with patch("vodoo.main.get_client", return_value=OdooClient(_config(), transport=transport)):
        result = CliRunner().invoke(main.app, args, input=content if stdin else None)
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["description"] == content
    assert len(transport.mock_calls) == 1
    sent = transport.create.call_args.args[1]["description"]
    if no_markdown:
        assert sent == content
    else:
        assert "<h1>Grüße</h1>" in sent
        assert "<strong>Résumé</strong>" in sent


@pytest.mark.parametrize("case", ["missing", "invalid_utf8", "directory", "conflict"])
def test_invalid_create_file_fails_before_client(tmp_path: Path, case: str) -> None:
    path = tmp_path / "task.md"
    if case == "invalid_utf8":
        path.write_bytes(b"\xff")
    elif case == "directory":
        path.mkdir()
    elif case == "conflict":
        path.write_text("# File", encoding="utf-8")
    args = [
        "--json",
        "project-task",
        "create",
        "Task",
        "--project",
        "2",
        "--description-file",
        str(path),
    ]
    if case == "conflict":
        args.extend(["--description", "inline"])
    with patch("vodoo.main.get_client") as get_client:
        result = CliRunner().invoke(main.app, args)
    assert result.exit_code != 0
    assert "error" in json.loads(result.output)
    get_client.assert_not_called()
