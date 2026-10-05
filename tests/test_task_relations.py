"""Read-only task relations: schema, batching, failures and CLI projections."""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import Iterator
from typing import Any

import pytest
from toon_format import decode
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo.base import configure_output
from vodoo.exceptions import OdooAccessError, RecordNotFoundError
from vodoo.main import app
from vodoo.task_relations import (
    TaskRelationError,
    UnsupportedTaskRelationError,
    async_resolve_task_relations,
    resolve_task_relations,
)


class Reader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[int], list[str] | None]] = []
        self.records: list[dict[str, Any]] | None = None
        self.error: Exception | None = None

    def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append((model, ids, fields))
        if self.error:
            raise self.error
        if self.records is not None:
            return self.records
        # Deliberately not request order: resolution must map by ID.
        return [
            {"id": record_id, "display_name": f"{model} #{record_id}"}
            for record_id in reversed(ids)
        ]


class AsyncReader:
    def __init__(self, reader: Reader) -> None:
        self.reader = reader

    async def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return self.reader.read(model, ids, fields)


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def asynchronous(request: pytest.FixtureRequest) -> bool:
    return bool(request.param)


def resolve(
    reader: Reader,
    task: dict[str, Any],
    asynchronous: bool,
    fields_info: dict[str, Any] | None = None,
) -> Any:
    if asynchronous:
        return asyncio.run(
            async_resolve_task_relations(AsyncReader(reader), task, fields_info=fields_info)
        )
    return resolve_task_relations(reader, task, fields_info=fields_info)


def test_all_relations_batch_order_and_raw_values(asynchronous: bool) -> None:
    reader = Reader()
    task = {
        "id": 42,
        "name": "Task",
        "tag_ids": [7, 2, 7],
        "user_ids": [9, 3],
        "project_id": [10, "Original project"],
        "stage_id": 5,
        "parent_id": (11, "Original parent"),
        "depend_on_ids": [15, 11],
        "dependent_ids": [16, 15],
        "description": "<p>unchanged</p>",
    }
    original = copy.deepcopy(task)
    result = resolve(reader, task, asynchronous)
    expected_ids = {
        "tag_ids": [2, 7],
        "user_ids": [3, 9],
        "project_id": [10],
        "stage_id": [5],
        "parent_id": [11],
        "depend_on_ids": [11, 15],
        "dependent_ids": [15, 16],
    }
    assert {
        field: [item["id"] for item in value] for field, value in result.items()
    } == expected_ids
    expected_models = {
        "tag_ids": "project.tags",
        "user_ids": "res.users",
        "project_id": "project.project",
        "stage_id": "project.task.type",
        "parent_id": "project.task",
        "depend_on_ids": "project.task",
        "dependent_ids": "project.task",
    }
    assert result == {
        field: [
            {"id": record_id, "name": f"{expected_models[field]} #{record_id}"} for record_id in ids
        ]
        for field, ids in expected_ids.items()
    }
    assert reader.calls == [
        ("project.tags", [2, 7], ["id", "display_name"]),
        ("res.users", [3, 9], ["id", "display_name"]),
        ("project.project", [10], ["id", "display_name"]),
        ("project.task.type", [5], ["id", "display_name"]),
        ("project.task", [11, 15, 16], ["id", "display_name"]),
    ]
    assert task == original


def test_empty_absent_and_metadata(asynchronous: bool) -> None:
    reader = Reader()
    task = {"id": 42, "tag_ids": [], "project_id": False, "parent_id": None, "user_ids": ()}
    result = resolve(reader, task, asynchronous, fields_info={key: {} for key in task})
    assert result == {"tag_ids": [], "user_ids": [], "project_id": [], "parent_id": []}
    assert reader.calls == []
    assert resolve(reader, {"name": "Task"}, asynchronous, fields_info={}) == {}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tag_ids", [1, "2"]),
        ("user_ids", [True]),
        ("depend_on_ids", [0]),
        ("dependent_ids", [1, [2, "name"]]),
        ("parent_id", [1]),
        ("project_id", [1, None]),
        ("stage_id", True),
        ("stage_id", -1),
        ("parent_id", "1"),
        ("tag_ids", 1),
        ("tag_ids", {}),
        ("stage_id", 1.5),
    ],
)
def test_malformed_values_fail_before_lookup(field: str, value: Any, asynchronous: bool) -> None:
    reader = Reader()
    with pytest.raises(TaskRelationError, match=field):
        resolve(reader, {"tag_ids": [4], field: value}, asynchronous)
    assert reader.calls == []


def test_metadata_unsupported_is_distinct(asynchronous: bool) -> None:
    reader = Reader()
    with pytest.raises(UnsupportedTaskRelationError, match=r"dependent_ids.*unsupported"):
        resolve(reader, {"dependent_ids": []}, asynchronous, fields_info={"tag_ids": {}})
    assert reader.calls == []


def test_missing_record(asynchronous: bool) -> None:
    reader = Reader()
    reader.records = [{"id": 3, "display_name": "Three"}]
    with pytest.raises(RecordNotFoundError) as error:
        resolve(reader, {"tag_ids": [3, 2]}, asynchronous)
    assert error.value.model == "project.tags"
    assert error.value.record_id == 2


@pytest.mark.parametrize(
    "records",
    [
        [{"id": 2}],
        [{"display_name": "Missing ID"}],
        [{"id": 2.0, "display_name": "Invalid float ID"}],
        [{"id": 2, "display_name": False}],
        [{"id": True, "display_name": "Invalid"}],
        [{"id": 9, "display_name": "Unrequested"}],
        [{"id": 2, "display_name": "One"}, {"id": 2, "display_name": "Duplicate"}],
    ],
)
def test_invalid_lookup_response(records: list[dict[str, Any]], asynchronous: bool) -> None:
    reader = Reader()
    reader.records = records
    with pytest.raises(TaskRelationError):
        resolve(reader, {"tag_ids": [2]}, asynchronous)


def test_access_failure_propagates(asynchronous: bool) -> None:
    reader = Reader()
    reader.error = OdooAccessError("Cannot read users")
    with pytest.raises(OdooAccessError) as error:
        resolve(reader, {"user_ids": [3]}, asynchronous)
    assert error.value is reader.error


@pytest.fixture(autouse=True)
def reset_output() -> Iterator[None]:
    main_module._console_config.update(simple=False, json=False, toon=False)
    configure_output(simple=False, json_mode=False, toon_mode=False)
    yield
    main_module._console_config.update(simple=False, json=False, toon=False)
    configure_output(simple=False, json_mode=False, toon_mode=False)


class Tasks:
    def __init__(self) -> None:
        self.task = {"id": 42, "name": "Task", "tag_ids": [2], "parent_id": False}
        self.fields: list[str] | None = None

    def get(self, task_id: int, fields: list[str] | None = None) -> dict[str, Any]:
        assert task_id == 42
        self.fields = fields
        return (
            self.task
            if fields is None
            else {key: value for key, value in self.task.items() if key in ["id", *fields]}
        )


class Client(Reader):
    def __init__(self) -> None:
        super().__init__()
        self.tasks = Tasks()


@pytest.mark.parametrize("fields", [[], ["name"], ["tag_ids"]])
@pytest.mark.parametrize("output_mode", ["--json", "--toon"])
@pytest.mark.parametrize("no_color", [False, True])
def test_show_additive_and_preserves_projection(
    monkeypatch: pytest.MonkeyPatch, fields: list[str], output_mode: str, no_color: bool
) -> None:
    client = Client()
    original = client.tasks.task.copy()
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    args = [*(["--no-color"] if no_color else []), output_mode, "project-task", "show", "42"]
    for field in fields:
        args.extend(["--field", field])
    result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    assert "\x1b[" not in result.output
    output = json.loads(result.output) if output_mode == "--json" else decode(result.output)
    assert client.tasks.fields == (fields or None)
    raw = client.tasks.get(42, fields or None)
    assert output == {**raw, "relations": resolve_task_relations(Reader(), raw)}
    assert client.tasks.task == original
    if fields == ["name"]:
        assert client.calls == []
        assert output["relations"] == {}


def test_show_lookup_failure_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = Client()
    client.records = []
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    result = CliRunner().invoke(app, ["--json", "project-task", "show", "42"])
    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "error": "Record 2 not found in project.tags",
        "type": "not_found",
    }
