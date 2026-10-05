"""Read-only task context contract, paging, failures and renderer coverage."""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import jsonschema
import pytest
from typer.testing import CliRunner

from vodoo.aio.project_tasks import AsyncTaskNamespace
from vodoo.exceptions import RecordNotFoundError
from vodoo.main import app
from vodoo.project_tasks import TaskNamespace
from vodoo.task_context import _RELATION_MODELS, CORE_FIELDS


def _task(full: bool = False) -> dict[str, Any]:
    task: dict[str, Any] = dict.fromkeys(CORE_FIELDS)
    task.update(
        id=42, name="Task [red]", description="<p>A\tB\nC</p>", write_date="2026-04-01 00:00:00"
    )
    task.update({name: [] for name in _RELATION_MODELS})
    if full:
        task.update(
            stage_id=[1, "old"],
            project_id=[2, "old"],
            tag_ids=[4, 3],
            user_ids=[5],
            parent_id=[6, "old"],
            depend_on_ids=[7],
            dependent_ids=[8],
        )
    return task


class _Client:
    def __init__(self, full: bool = False) -> None:
        self.task = _task(full)
        self.config = SimpleNamespace(url="https://odoo.example/")
        self.is_json2 = True
        self.calls: list[tuple[str, Any]] = []
        self.data: dict[str, list[dict[str, Any]]] = {
            "mail.message": [
                {"id": i, "body": "[red]\ttext\nnext", "attachment_ids": [20]} for i in range(1, 4)
            ]
            if full
            else [],
            "ir.attachment": [{"id": 20, "name": "file.pdf"}] if full else [],
        }
        self.failure: tuple[str, int] | None = None
        self.short_pages = False
        self.unordered = False
        self.missing_relation = False
        self.definitions = {name: {"type": "char"} for name in self.task}

    def fields_get(self, model: str, **_kwargs: Any) -> dict[str, Any]:
        self.calls.append(("fields_get", model))
        if self.failure == ("fields_get", 0):
            raise PermissionError("metadata forbidden")
        return self.definitions

    def read(self, model: str, ids: list[int], fields: list[str]) -> list[dict[str, Any]]:
        self.calls.append(("read", (model, ids, fields)))
        if model == "project.task" and ids == [42]:
            if self.failure == ("task", 0):
                raise PermissionError("task forbidden")
            return [{name: self.task[name] for name in fields if name in self.task}]
        if self.missing_relation:
            return []
        return [{"id": i, "display_name": f"Resolved {i}"} for i in reversed(ids)]

    def search_read(self, model: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("search_read", (model, kwargs)))
        assert kwargs["order"] == "id asc"
        after_id = kwargs["domain"][-1][2]
        if self.failure == (model, after_id):
            raise PermissionError("section forbidden")
        if self.unordered and model == "mail.message":
            return [{"id": 1}, {"id": 1}]
        limit = 1 if self.short_pages else kwargs["limit"]
        return copy.deepcopy([row for row in self.data[model] if row["id"] > after_id][:limit])

    def create(self, *_args: Any, **_kwargs: Any) -> None:
        pytest.fail("context must never create")

    def write(self, *_args: Any, **_kwargs: Any) -> None:
        pytest.fail("context must never write")

    def unlink(self, *_args: Any, **_kwargs: Any) -> None:
        pytest.fail("context must never unlink")


class _AsyncClient:
    def __init__(self, client: _Client) -> None:
        self.client = client
        self.config = client.config
        self.is_json2 = client.is_json2

    async def read(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self.client.read(*args, **kwargs)

    async def fields_get(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self.client.fields_get(*args, **kwargs)

    async def search_read(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self.client.search_read(*args, **kwargs)


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def run_context(request: pytest.FixtureRequest) -> Any:
    def run(client: _Client, **kwargs: Any) -> dict[str, Any]:
        if request.param:
            ns = AsyncTaskNamespace(_AsyncClient(client))  # type: ignore[arg-type]
            result = asyncio.run(ns.context(42, **kwargs))
        else:
            result = TaskNamespace(client).context(42, **kwargs)  # type: ignore[arg-type]
        schema = json.loads(Path("spec/v1/task-context.schema.json").read_text())
        jsonschema.validate(result, schema)
        return result

    return run


@pytest.mark.parametrize("full", [False, True])
def test_empty_and_full_context(run_context: Any, full: bool) -> None:
    client = _Client(full)
    original = copy.deepcopy(client.task)
    result = run_context(client, page_size=2)
    assert result["complete"] is True
    assert result["errors"] == []
    assert result["task"] == original == client.task
    assert result["write_date"] == original["write_date"]
    assert result["url"] == "https://odoo.example/odoo/project.task/42"
    assert set(result["relations"]) == set(_RELATION_MODELS)
    if full:
        assert result["relations"]["tag_ids"] == [
            {"id": 3, "name": "Resolved 3"},
            {"id": 4, "name": "Resolved 4"},
        ]
        assert all(result["relations"].values())
        assert len(result["messages"]) == 3
        assert len(result["attachments"]) == 1
        attachment_calls = [
            args
            for method, args in client.calls
            if method == "search_read" and args[0] == "ir.attachment"
        ]
        assert ("id", "in", [20]) in attachment_calls[0][1]["domain"]
    else:
        assert not any(result["relations"].values())
        assert result["messages"] == result["attachments"] == []
    assert all(status["continuation"] is None for status in result["pagination"].values())


def test_short_server_pages_are_exhausted(run_context: Any) -> None:
    client = _Client(True)
    client.short_pages = True
    result = run_context(client, page_size=100)
    assert result["complete"] is True
    assert [row["id"] for row in result["messages"]] == [1, 2, 3]


def test_truncation_and_exact_page_cap(run_context: Any) -> None:
    result = run_context(_Client(True), page_size=2, max_pages=1)
    assert result["complete"] is False
    assert result["errors"] == []
    status = result["pagination"]["messages"]
    assert status["count"] == 2
    assert status["complete"] is False
    assert status["continuation"]["after_id"] == 2
    assert status["continuation"]["domain"][-1] == ("id", ">", 2)
    assert result["pagination"]["attachments"]["complete"] is True
    result = run_context(_Client(True), page_size=3, max_pages=1)
    assert result["complete"] is True


@pytest.mark.parametrize(
    "failure", [("mail.message", 2), ("ir.attachment", 0), ("task", 0), ("fields_get", 0)]
)
def test_section_failures_are_explicit(run_context: Any, failure: tuple[str, int]) -> None:
    client = _Client(True)
    client.failure = failure
    result = run_context(client, page_size=2)
    assert result["complete"] is False
    assert result["errors"][0]["type"] == "PermissionError"
    assert result["url"] is not None
    if failure[0] == "mail.message":
        assert len(result["messages"]) == 2
        assert result["pagination"]["messages"]["continuation"]["after_id"] == 2
        assert result["attachments"]
    elif failure[0] == "task":
        assert result["task"] is None
        assert any(error["section"] == "relations" for error in result["errors"])


def test_unsupported_reverse_dependency_is_not_empty(run_context: Any) -> None:
    client = _Client()
    del client.definitions["dependent_ids"]
    result = run_context(client)
    assert result["complete"] is False
    assert "dependent_ids" not in result["relations"]
    assert any(
        error["section"] == "relations"
        and error["type"] == "unsupported_fields"
        and error["fields"] == ["dependent_ids"]
        for error in result["errors"]
    )


def test_missing_projected_field_is_not_claimed_unsupported(run_context: Any) -> None:
    client = _Client()
    del client.task["dependent_ids"]
    result = run_context(client)
    assert result["complete"] is False
    assert all(error["type"] != "unsupported_fields" for error in result["errors"])


def test_missing_related_record_is_explicit(run_context: Any) -> None:
    client = _Client(True)
    client.missing_relation = True
    result = run_context(client)
    assert result["complete"] is False
    assert result["errors"][0]["section"] == "relations"
    assert result["errors"][0]["type"] == "RecordNotFoundError"
    assert result["task"]["stage_id"] == [1, "old"]


def test_nonadvancing_pages_cannot_loop(run_context: Any) -> None:
    client = _Client(True)
    client.unordered = True
    result = run_context(client)
    assert result["complete"] is False
    assert result["errors"][0]["section"] == "messages"
    assert result["pagination"]["messages"]["continuation"]["after_id"] == 0


def test_custom_fields_are_additive_and_url_uses_dialect(run_context: Any) -> None:
    client = _Client()
    client.task["custom"] = "value"
    client.definitions["custom"] = {"type": "char"}
    client.is_json2 = False
    result = run_context(client, fields=["custom"])
    assert result["task"]["custom"] == "value"
    assert result["task"]["description"]
    assert result["url"] == "https://odoo.example/web#id=42&model=project.task&view_type=form"


def test_missing_task_raises_not_found(run_context: Any) -> None:
    client = _Client()
    with patch.object(client, "read", return_value=[]), pytest.raises(RecordNotFoundError):
        run_context(client)


@pytest.mark.parametrize(("page_size", "max_pages"), [(0, None), (2, 0), (-1, 1)])
def test_invalid_paging_does_not_read(
    run_context: Any, page_size: int, max_pages: int | None
) -> None:
    client = _Client()
    with pytest.raises(ValueError, match="must be positive"):
        run_context(client, page_size=page_size, max_pages=max_pages)
    assert client.calls == []


@pytest.mark.parametrize("mode", ["--json", "--toon", "--simple"])
@pytest.mark.parametrize("complete", [False, True])
def test_cli_payload_and_exit(mode: str, complete: bool) -> None:
    payload = TaskNamespace(_Client(True)).context(42)  # type: ignore[arg-type]
    payload["complete"] = complete
    if not complete:
        payload["errors"] = [
            {"section": "relations", "type": "PermissionError", "message": "Denied"}
        ]
    tasks = MagicMock()
    tasks.context.return_value = payload
    with patch("vodoo.main.get_client", return_value=MagicMock(tasks=tasks)):
        result = CliRunner().invoke(
            app,
            [
                mode,
                "project-task",
                "context",
                "42",
                "-f",
                "custom",
                "--page-size",
                "2",
                "--max-pages",
                "1",
            ],
        )
    assert result.exit_code == (0 if complete else 1)
    tasks.context.assert_called_once_with(42, fields=["custom"], page_size=2, max_pages=1)
    assert "\x1b" not in result.output
    if mode == "--json":
        assert json.loads(result.output) == payload
    elif mode == "--simple":
        lines = result.output.splitlines()
        assert len(lines) == len(payload)
        assert {
            key: json.loads(value) for key, value in (line.split("\t", 1) for line in lines)
        } == payload
    else:
        assert "schema_version: 1" in result.output
        assert "complete: " + str(complete).lower() in result.output
        if not complete:
            assert "PermissionError" in result.output
