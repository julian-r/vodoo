"""Tests for comment and note message IDs."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from toon_format import decode, encode
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo.aio.auth import (
    message_post_sudo as async_message_post_sudo,
)
from vodoo.aio.auth import (
    message_post_sudo_with_id as async_message_post_sudo_with_id,
)
from vodoo.aio.project_tasks import AsyncTaskNamespace
from vodoo.auth import message_post_sudo, message_post_sudo_with_id
from vodoo.base import configure_output
from vodoo.exceptions import RecordNotFoundError
from vodoo.project_tasks import TaskNamespace


@pytest.fixture(autouse=True)
def reset_output_state() -> Iterator[None]:
    """Keep CLI output globals from leaking between parametrized invocations."""
    defaults = {"simple": False, "json": False, "toon": False}
    main_module._console_config.update(defaults)
    configure_output()
    yield
    main_module._console_config.update(defaults)
    configure_output()


def _sync_client(message_id: int = 9766) -> MagicMock:
    client = MagicMock()
    client.read.return_value = [{"partner_id": [7, "Author"]}]
    client.search_read.return_value = [{"res_id": 1}]
    client.create.return_value = message_id
    return client


def _async_client(message_id: int = 9766) -> MagicMock:
    client = MagicMock()
    client.read = AsyncMock(return_value=[{"partner_id": [7, "Author"]}])
    client.search_read = AsyncMock(return_value=[{"res_id": 1}])
    client.create = AsyncMock(return_value=message_id)
    return client


def test_message_post_sudo_preserves_bool_and_id_contracts() -> None:
    client = _sync_client()

    success = message_post_sudo(client, "project.task", 189, "<p>Done</p>", user_id=3)
    message_id = message_post_sudo_with_id(client, "project.task", 189, "<p>Done</p>", user_id=3)

    assert success is True
    assert type(message_id) is int
    assert message_id == 9766


def test_message_subtypes_use_stable_external_ids_and_are_required() -> None:
    client = _sync_client()
    message_post_sudo_with_id(client, "project.task", 189, "Done", user_id=3)
    client.search_read.assert_called_once_with(
        "ir.model.data",
        domain=[("module", "=", "mail"), ("name", "=", "mt_comment")],
        fields=["res_id"],
        limit=1,
    )

    for invalid_rows in ([], [{"res_id": 0}], [{"res_id": -1}], [{"res_id": True}]):
        client.search_read.return_value = invalid_rows
        with pytest.raises(RecordNotFoundError):
            message_post_sudo_with_id(client, "project.task", 189, "Note", user_id=3, is_note=True)


def test_async_message_post_sudo_preserves_bool_and_id_contracts() -> None:
    async def exercise() -> tuple[bool, int]:
        client = _async_client()
        success = await async_message_post_sudo(
            client, "project.task", 189, "<p>Done</p>", user_id=3
        )
        message_id = await async_message_post_sudo_with_id(
            client, "project.task", 189, "<p>Done</p>", user_id=3
        )
        return success, message_id

    success, message_id = asyncio.run(exercise())

    assert success is True
    assert type(message_id) is int
    assert message_id == 9766


@pytest.mark.parametrize("command", ["comment", "note"])
def test_domain_message_apis_preserve_bool_and_id_contracts(command: str) -> None:
    namespace = TaskNamespace(_sync_client())

    success = getattr(namespace, command)(189, "Done", user_id=3)
    message_id = getattr(namespace, f"{command}_with_id")(189, "Done", user_id=3)

    assert success is True
    assert type(message_id) is int
    assert message_id == 9766


@pytest.mark.parametrize("command", ["comment", "note"])
def test_async_domain_message_apis_preserve_bool_and_id_contracts(command: str) -> None:
    async def exercise() -> tuple[bool, int]:
        namespace = AsyncTaskNamespace(_async_client())
        success = await getattr(namespace, command)(189, "Done", user_id=3)
        message_id = await getattr(namespace, f"{command}_with_id")(189, "Done", user_id=3)
        return success, message_id

    success, message_id = asyncio.run(exercise())

    assert success is True
    assert type(message_id) is int
    assert message_id == 9766


def _decode_output(output_format: str, output: str) -> Any:
    decoder: Callable[[str], Any] = json.loads if output_format == "json" else decode
    return decoder(output)


@pytest.mark.parametrize("output_format", ["json", "toon"])
@pytest.mark.parametrize(("command", "message_id"), [("comment", 9766), ("note", 9767)])
def test_project_task_structured_output_includes_message_id(
    output_format: str,
    command: str,
    message_id: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    getattr(client.tasks, f"{command}_with_id").return_value = message_id
    monkeypatch.setattr(main_module, "get_client", lambda: client)

    result = CliRunner().invoke(
        main_module.app,
        [f"--{output_format}", "project-task", command, "189", "Automated update"],
    )

    assert result.exit_code == 0
    assert _decode_output(output_format, result.stdout) == {
        "ok": True,
        "id": 189,
        "message_id": message_id,
        "action": command,
    }


@pytest.mark.parametrize("output_format", ["json", "toon"])
@pytest.mark.parametrize("command", ["comment", "note"])
def test_project_task_structured_failure_is_single_parseable_payload(
    output_format: str,
    command: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock()
    getattr(client.tasks, f"{command}_with_id").return_value = 0
    monkeypatch.setattr(main_module, "get_client", lambda: client)

    result = CliRunner().invoke(
        main_module.app,
        [f"--{output_format}", "project-task", command, "189", "Automated update"],
    )

    expected = {
        "error": f"Failed to add {command} to task 189",
        "type": "vodoo_error",
    }
    assert result.exit_code == 1
    assert _decode_output(output_format, result.stdout) == expected
    if output_format == "toon":
        assert result.stdout == f"{encode(expected)}\n"
