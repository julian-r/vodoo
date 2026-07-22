"""Tests for the CLI --no-color output option."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from vodoo import main
from vodoo.projects import display_stages

_ESC = b"\x1b"
_DEFAULT_CONSOLE_CONFIG = {"simple": False, "json": False, "toon": False, "no_color": False}


def _set_console_config(config: dict[str, bool]) -> None:
    main._console_config.clear()
    main._console_config.update(config)
    main._apply_output_config(no_color=config["no_color"])


@pytest.fixture(autouse=True)
def isolate_output_config() -> Iterator[None]:
    """Prevent CLI module state from leaking into or out of these tests."""
    original_console_config = main._console_config.copy()
    original_instance_config = main._instance_config.copy()
    _set_console_config(_DEFAULT_CONSOLE_CONFIG)
    main._instance_config.update(name=None)
    try:
        yield
    finally:
        _set_console_config(original_console_config)
        main._instance_config.clear()
        main._instance_config.update(original_instance_config)


def _run_cli_forced_terminal(*args: str) -> tuple[int, bytes]:
    """Run the installed CLI with Rich terminal styling forced on."""
    env = os.environ.copy()
    env.pop("NO_COLOR", None)
    env["FORCE_COLOR"] = "1"
    executable = shutil.which("vodoo")
    assert executable is not None
    result = subprocess.run(
        [executable, *args],
        capture_output=True,
        check=False,
        env=env,
        timeout=10,
    )
    return result.returncode, result.stdout + result.stderr


def test_forced_terminal_harness_detects_default_ansi_output() -> None:
    """Prove the regression harness is capable of observing Rich styling."""
    exit_code, output = _run_cli_forced_terminal("--help")

    assert exit_code == 0
    assert _ESC in output


@pytest.mark.parametrize(
    ("args", "expected", "exit_code"),
    [
        (("--no-color", "--help"), b"Usage:", 0),
        (("project-task", "--no-color", "--help"), b"Project task operations", 0),
        (("--no-color", "--version"), b"vodoo version", 0),
        (("--no-color", "--invalid-option"), b"No such option", 2),
    ],
)
def test_no_color_disables_ansi_before_argument_parsing(
    args: tuple[str, ...],
    expected: bytes,
    exit_code: int,
) -> None:
    """Help, eager options, and parser errors are unstyled in a real terminal."""
    actual_exit_code, output = _run_cli_forced_terminal(*args)

    assert actual_exit_code == exit_code
    assert expected in output
    assert _ESC not in output


def test_global_no_color_disables_ansi_for_project_task_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The automation command from issue #56 produces unstyled output."""
    client = Mock()
    client.tasks.get.return_value = {
        "name": "ODP-189",
        "description": "Automation task",
        "tag_ids": [3],
        "stage_id": [2, "In Progress"],
    }
    monkeypatch.setattr(main, "get_client", Mock(return_value=client))

    result = CliRunner().invoke(
        main.app,
        [
            "--no-color",
            "project-task",
            "show",
            "189",
            "-f",
            "name",
            "-f",
            "description",
            "-f",
            "tag_ids",
            "-f",
            "stage_id",
        ],
        color=True,
    )

    assert result.exit_code == 0
    assert "Task #189" in result.output
    assert "ODP-189" in result.output
    assert "\x1b" not in result.output
    client.tasks.get.assert_called_once_with(
        189,
        fields=["name", "description", "tag_ids", "stage_id"],
    )


def test_subcommand_no_color_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Output options remain usable after the command group name."""
    client = Mock()
    client.tasks.get.return_value = {"name": "ODP-189"}
    monkeypatch.setattr(main, "get_client", Mock(return_value=client))

    result = CliRunner().invoke(
        main.app,
        ["project-task", "--no-color", "show", "189", "-f", "name"],
        color=True,
    )

    assert result.exit_code == 0
    assert "\x1b" not in result.output


def test_no_color_applies_to_project_stage_tables(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Project stage tables switch from styled to unstyled output."""
    display_stages([{"id": 2, "name": "In Progress", "sequence": 10, "fold": False}])
    styled_output = capsys.readouterr().out

    main._apply_output_config(no_color=True)
    display_stages([{"id": 2, "name": "In Progress", "sequence": 10, "fold": False}])
    unstyled_output = capsys.readouterr().out

    assert "\x1b" in styled_output
    assert "In Progress" in unstyled_output
    assert "\x1b" not in unstyled_output
