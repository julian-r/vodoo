"""Tests for --toon output mode."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from toon_format import decode
from typer.testing import CliRunner

from vodoo import main
from vodoo.base import configure_output, toon_print


@pytest.fixture(autouse=True)
def reset_output_config() -> Any:
    """Prevent process-global CLI output settings from leaking between tests."""
    main._console_config.update({"simple": False, "json": False, "toon": False})
    configure_output(simple=False, json_mode=False, toon_mode=False)
    yield
    main._console_config.update({"simple": False, "json": False, "toon": False})
    configure_output(simple=False, json_mode=False, toon_mode=False)


def test_toon_print_encodes_data(capsys: pytest.CaptureFixture[str]) -> None:
    toon_print({"ok": True, "id": 189})

    assert decode(capsys.readouterr().out) == {"ok": True, "id": 189}


def test_mutating_command_returns_toon(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, str]] = []

    def comment_with_id(task_id: int, message: str, **kwargs: Any) -> int:  # noqa: ARG001
        calls.append((task_id, message))
        return 9766

    client = SimpleNamespace(tasks=SimpleNamespace(comment_with_id=comment_with_id))
    monkeypatch.setattr(main, "get_client", lambda: client)

    result = CliRunner().invoke(
        main.app,
        ["--toon", "project-task", "comment", "189", "Deployed to staging"],
    )

    assert result.exit_code == 0
    assert calls == [(189, "Deployed to staging")]
    assert decode(result.stdout) == {
        "ok": True,
        "id": 189,
        "message_id": 9766,
        "action": "comment",
    }
