"""Tests for the CLI --no-color output option."""

from __future__ import annotations

from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from vodoo import main
from vodoo.projects import display_stages


def test_global_no_color_disables_ansi_for_project_task_show(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The automation command from issue #56 produces unstyled output."""
    main._apply_output_config(no_color=False)
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
    assert "\x1b[" not in result.output
    client.tasks.get.assert_called_once_with(
        189,
        fields=["name", "description", "tag_ids", "stage_id"],
    )


def test_subcommand_no_color_is_supported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Output options remain usable after the command group name."""
    main._apply_output_config(no_color=False)
    client = Mock()
    client.tasks.get.return_value = {"name": "ODP-189"}
    monkeypatch.setattr(main, "get_client", Mock(return_value=client))

    result = CliRunner().invoke(
        main.app,
        ["project-task", "--no-color", "show", "189", "-f", "name"],
        color=True,
    )

    assert result.exit_code == 0
    assert "\x1b[" not in result.output


def test_no_color_applies_to_project_stage_tables(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Display helpers use the CLI's configured console rather than a new colored one."""
    main._apply_output_config(no_color=True)

    display_stages([{"id": 2, "name": "In Progress", "sequence": 10, "fold": False}])

    output = capsys.readouterr().out
    assert "In Progress" in output
    assert "\x1b[" not in output
