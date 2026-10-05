"""Atomic task creation tests: real namespaces/clients with mocked transports only."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import click
import pytest
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo.aio.client import AsyncOdooClient
from vodoo.aio.transport import AsyncOdooTransport
from vodoo.base import configure_output
from vodoo.client import OdooClient
from vodoo.config import OdooConfig
from vodoo.content import HTML
from vodoo.exceptions import RecordOperationError
from vodoo.transport import OdooTransport


@pytest.fixture(autouse=True)
def _reset_output() -> Iterator[None]:
    main_module._console_config.update(simple=False, json=False, toon=False)
    configure_output(simple=False, json_mode=False, toon_mode=False)
    yield
    main_module._console_config.update(simple=False, json=False, toon=False)
    configure_output(simple=False, json_mode=False, toon_mode=False)


def _config() -> OdooConfig:
    return OdooConfig(
        url="https://odoo.example.test",
        database="test",
        username="test",
        password="test",
    )


def _create(async_mode: bool, transport: MagicMock, values: dict[str, Any]) -> int:
    if async_mode:
        client = AsyncOdooClient(_config(), transport=transport)
        return asyncio.run(client.tasks.create(**values))
    client_sync = OdooClient(_config(), transport=transport)
    return client_sync.tasks.create(**values)


def _transport(async_mode: bool = False) -> MagicMock:
    transport = MagicMock(spec=AsyncOdooTransport if async_mode else OdooTransport)
    if async_mode:
        transport.create = AsyncMock(return_value=123)
    else:
        transport.create.return_value = 123
    return transport


@pytest.mark.parametrize("async_mode", [False, True])
def test_complete_task_is_one_create_with_serialized_relations(async_mode: bool) -> None:
    transport = _transport(async_mode)

    assert (
        _create(
            async_mode,
            transport,
            {
                "name": "Task title",
                "project_id": 2,
                "description": "**Details**",
                "stage_id": 15,
                "tag_ids": [2, 5],
                "user_ids": [5, 6],
                "parent_id": 100,
                "depend_on_ids": [90, 91],
                "priority": "1",
            },
        )
        == 123
    )

    expected = {
        "name": "Task title",
        "project_id": 2,
        "description": "<p><strong>Details</strong></p>",
        "stage_id": 15,
        "tag_ids": [(6, 0, [2, 5])],
        "user_ids": [(6, 0, [5, 6])],
        "parent_id": 100,
        "depend_on_ids": [(6, 0, [90, 91])],
        "priority": "1",
    }
    assert transport.mock_calls == [
        call.create("project.task", expected, {"default_project_id": 2})
    ]
    # On the wire, command tuples become JSON arrays, never raw bare ID lists.
    assert json.loads(json.dumps(expected))["depend_on_ids"] == [[6, 0, [90, 91]]]
    if async_mode:
        transport.create.assert_awaited_once()


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize(
    "field", ["project_id", "stage_id", "parent_id", "tag_ids", "user_ids", "depend_on_ids"]
)
@pytest.mark.parametrize("invalid_id", [0, -1, True, False, 1.5, "5", None])
def test_invalid_ids_fail_before_any_request(async_mode: bool, field: str, invalid_id: Any) -> None:
    transport = _transport(async_mode)
    if invalid_id is None and field in {"stage_id", "parent_id"}:
        # None means the optional many2one was not supplied, rather than ID zero.
        assert _create(async_mode, transport, {"name": "Task", "project_id": 2, field: None}) == 123
        assert transport.mock_calls == [
            call.create(
                "project.task", {"name": "Task", "project_id": 2}, {"default_project_id": 2}
            )
        ]
        return
    values: dict[str, Any] = {"name": "Task", "project_id": 2}
    values[field] = [5, invalid_id] if field.endswith("_ids") else invalid_id

    with pytest.raises(ValueError, match=f"{field} must contain only positive integer IDs"):
        _create(async_mode, transport, values)

    assert transport.mock_calls == []


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("explicit_empty", [False, True])
def test_optional_relations_are_omitted_or_explicitly_empty(
    async_mode: bool, explicit_empty: bool
) -> None:
    transport = _transport(async_mode)
    values: dict[str, Any] = {"name": "Task", "project_id": 2}
    expected = dict(values)
    if explicit_empty:
        values.update(user_ids=[], tag_ids=[], depend_on_ids=[], description="")
        expected.update(
            user_ids=[(6, 0, [])], tag_ids=[(6, 0, [])], depend_on_ids=[(6, 0, [])], description=""
        )

    assert _create(async_mode, transport, values) == 123
    assert transport.mock_calls == [
        call.create("project.task", expected, {"default_project_id": 2})
    ]


@pytest.mark.parametrize("async_mode", [False, True])
def test_html_description_is_not_reinterpreted_as_markdown(async_mode: bool) -> None:
    transport = _transport(async_mode)
    raw_html = "<p>**Keep literal**</p>"

    assert (
        _create(
            async_mode, transport, {"name": "Task", "project_id": 2, "description": HTML(raw_html)}
        )
        == 123
    )
    assert transport.create.call_args.args[1]["description"] == raw_html


@pytest.mark.parametrize("async_mode", [False, True])
def test_create_failure_never_attempts_a_patch_or_fallback(async_mode: bool) -> None:
    transport = _transport(async_mode)
    transport.create.side_effect = RecordOperationError("Cannot create task")

    with pytest.raises(RecordOperationError, match="Cannot create task"):
        _create(async_mode, transport, {"name": "Task", "project_id": 2, "stage_id": 15})

    assert transport.mock_calls == [
        call.create(
            "project.task",
            {"name": "Task", "project_id": 2, "stage_id": 15},
            {"default_project_id": 2},
        )
    ]


def _invoke(arguments: list[str], transport: MagicMock) -> Any:
    client = OdooClient(_config(), transport=transport)
    with patch("vodoo.main.get_client", return_value=client):
        return CliRunner().invoke(main_module.app, arguments)


@pytest.mark.parametrize(
    "title_args", [["Task title"], ["--name", "Task title"], ["--title", "Task title"]]
)
def test_cli_complete_create_returns_id_and_requested_fields(title_args: list[str]) -> None:
    transport = _transport()
    result = _invoke(
        [
            "--json",
            "project-task",
            "create",
            *title_args,
            "--project",
            "2",
            "--description",
            "**Details**",
            "--stage",
            "15",
            "--tag",
            "2",
            "--tag",
            "5",
            "--assignee",
            "5",
            "--user",
            "6",
            "--parent",
            "100",
            "--depends-on",
            "90",
            "--depends-on",
            "91",
        ],
        transport,
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "ok": True,
        "id": 123,
        "name": "Task title",
        "project_id": 2,
        "description": "**Details**",
        "stage_id": 15,
        "tag_ids": [2, 5],
        "user_ids": [5, 6],
        "parent_id": 100,
        "depend_on_ids": [90, 91],
    }
    assert transport.mock_calls == [
        call.create(
            "project.task",
            {
                "name": "Task title",
                "project_id": 2,
                "description": "<p><strong>Details</strong></p>",
                "stage_id": 15,
                "tag_ids": [(6, 0, [2, 5])],
                "user_ids": [(6, 0, [5, 6])],
                "parent_id": 100,
                "depend_on_ids": [(6, 0, [90, 91])],
            },
            {"default_project_id": 2},
        )
    ]


def test_cli_legacy_positional_user_desc_flags_remain_supported() -> None:
    transport = _transport()
    result = _invoke(
        ["project-task", "--simple", "create", "Task", "-p", "2", "--user", "5", "--desc", "# D"],
        transport,
    )

    assert result.exit_code == 0, result.output
    assert "Successfully created task 'Task' with ID 123" in result.output
    assert transport.mock_calls == [
        call.create(
            "project.task",
            {
                "name": "Task",
                "project_id": 2,
                "user_ids": [(6, 0, [5])],
                "description": "<h1>D</h1>",
            },
            {"default_project_id": 2},
        )
    ]


@pytest.mark.parametrize(
    "flag", ["--project", "--stage", "--parent", "--tag", "--assignee", "--user", "--depends-on"]
)
@pytest.mark.parametrize("invalid_id", ["0", "-1"])
@pytest.mark.parametrize("mode", ["--json", "--simple"])
def test_cli_invalid_relation_ids_fail_before_get_client(
    flag: str, invalid_id: str, mode: str
) -> None:
    arguments = ["project-task", mode, "create", "Task"]
    if flag != "--project":
        arguments.extend(["--project", "2"])
    if flag in {"--tag", "--assignee", "--user", "--depends-on"}:
        arguments.extend([flag, "5"])  # A later invalid repeat must still fail.
    arguments.extend([flag, invalid_id])
    with patch("vodoo.main.get_client") as get_client:
        result = CliRunner().invoke(main_module.app, arguments)

    assert result.exit_code == 2
    assert "positive integer IDs" in result.output
    if mode == "--json":
        assert json.loads(result.output)["type"] == "validation"
    get_client.assert_not_called()


@pytest.mark.parametrize(
    "arguments",
    [[], ["--name", ""], [" "], ["Task", "--name", "Task"], ["Task", "--title", "Other"]],
)
def test_cli_missing_blank_or_conflicting_title_fails_before_get_client(
    arguments: list[str],
) -> None:
    with patch("vodoo.main.get_client") as get_client:
        result = CliRunner().invoke(
            main_module.app, ["--json", "project-task", "create", "--project", "2", *arguments]
        )

    assert result.exit_code == 2
    assert json.loads(result.output)["type"] == "validation"
    get_client.assert_not_called()


def test_cli_minimal_json_omits_unspecified_fields() -> None:
    transport = _transport()
    result = _invoke(["--json", "project-task", "create", "Task", "--project", "2"], transport)

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {"ok": True, "id": 123, "name": "Task", "project_id": 2}
    assert transport.mock_calls == [
        call.create("project.task", {"name": "Task", "project_id": 2}, {"default_project_id": 2})
    ]


def test_cli_project_is_still_required() -> None:
    with patch("vodoo.main.get_client") as get_client:
        result = CliRunner().invoke(main_module.app, ["project-task", "create", "Task"])

    assert result.exit_code == 2
    assert "--project" in click.unstyle(result.output)
    get_client.assert_not_called()


def test_cli_no_markdown_sends_and_returns_raw_description() -> None:
    transport = _transport()
    raw_html = "<p>**Keep literal**</p>"
    result = _invoke(
        [
            "--json",
            "project-task",
            "create",
            "Task",
            "--project",
            "2",
            "--desc",
            raw_html,
            "--no-markdown",
        ],
        transport,
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["description"] == raw_html
    assert transport.create.call_args.args[1]["description"] == raw_html
    assert len(transport.mock_calls) == 1


def test_cli_failed_create_returns_error_without_any_other_mutation() -> None:
    transport = _transport()
    transport.create.side_effect = RecordOperationError("Cannot create task")
    result = _invoke(["--json", "project-task", "create", "Task", "--project", "2"], transport)

    assert result.exit_code == 1
    assert json.loads(result.output) == {"error": "Cannot create task", "type": "vodoo_error"}
    assert len(transport.mock_calls) == 1
    transport.write.assert_not_called()


def test_cli_help_documents_complete_atomic_create() -> None:
    result = CliRunner().invoke(main_module.app, ["project-task", "create", "--help"])

    assert result.exit_code == 0
    output = click.unstyle(result.output)
    for flag in (
        "--name",
        "--title",
        "--description",
        "--desc",
        "--stage",
        "--tag",
        "--assignee",
        "--user",
        "--parent",
        "--depends-on",
        "--no-markdown",
    ):
        assert flag in output
    assert "atomic request" in output
    assert "--depends-on 90 --depends-on 91" in output
