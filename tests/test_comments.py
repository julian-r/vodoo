"""Tests for comment and note message IDs."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

from vodoo.aio.auth import message_post_sudo as async_message_post_sudo
from vodoo.auth import message_post_sudo
from vodoo.base import configure_output
from vodoo.main import app


def test_message_post_sudo_returns_created_message_id() -> None:
    client = MagicMock()
    client.read.return_value = [{"partner_id": [7, "Author"]}]
    client.search.return_value = [1]
    client.create.return_value = 9766

    message_id = message_post_sudo(client, "project.task", 189, "<p>Done</p>", user_id=3)

    assert message_id == 9766


def test_async_message_post_sudo_returns_created_message_id() -> None:
    client = MagicMock()
    client.read = AsyncMock(return_value=[{"partner_id": [7, "Author"]}])
    client.search = AsyncMock(return_value=[1])
    client.create = AsyncMock(return_value=9766)

    message_id = asyncio.run(
        async_message_post_sudo(client, "project.task", 189, "<p>Done</p>", user_id=3)
    )

    assert message_id == 9766


@pytest.mark.parametrize(("command", "message_id"), [("comment", 9766), ("note", 9767)])
def test_project_task_structured_output_includes_message_id(
    command: str,
    message_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    getattr(client.tasks, f"{command}_with_id").return_value = message_id
    monkeypatch.setattr("vodoo.main.get_client", lambda: client)

    try:
        result = CliRunner().invoke(
            app, ["--json", "project-task", command, "189", "Automated update"]
        )
    finally:
        configure_output()

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "ok": True,
        "id": 189,
        "message_id": message_id,
        "action": command,
    }
