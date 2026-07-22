"""Tests for project milestone workflows."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from typer.testing import CliRunner

from vodoo.aio.project_tasks import AsyncTaskNamespace
from vodoo.aio.projects import AsyncProjectNamespace
from vodoo.exceptions import RecordNotFoundError, RecordOperationError, VodooError
from vodoo.main import app
from vodoo.project_tasks import TaskNamespace
from vodoo.projects import MILESTONE_FIELDS, MILESTONE_TASK_FIELDS, ProjectNamespace


class _StubClient:
    def __init__(
        self,
        search_results: list[list[dict[str, Any]]] | None = None,
        read_results: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self.search_results = list(search_results or [])
        self.read_results = list(read_results or [])
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def search_read(self, model: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("search_read", (model, *args), kwargs))
        return self.search_results.pop(0)

    def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("read", (model, ids), {"fields": fields}))
        return self.read_results.pop(0)

    def create(self, model: str, values: dict[str, Any], **kwargs: Any) -> int:
        self.calls.append(("create", (model, values), kwargs))
        return 91

    def write(self, model: str, ids: list[int], values: dict[str, Any]) -> bool:
        self.calls.append(("write", (model, ids, values), {}))
        return True


class _StubAsyncClient(_StubClient):
    async def search_read(self, model: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return super().search_read(model, *args, **kwargs)

    async def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return super().read(model, ids, fields)

    async def create(self, model: str, values: dict[str, Any], **kwargs: Any) -> int:
        return super().create(model, values, **kwargs)

    async def write(self, model: str, ids: list[int], values: dict[str, Any]) -> bool:
        return super().write(model, ids, values)


class TestProjectMilestoneNamespace:
    def test_list_resolves_exact_project_name(self) -> None:
        client = _StubClient([[{"id": 7, "name": "Website"}], [{"id": 3, "name": "Beta"}]])
        namespace = ProjectNamespace(client=client)  # type: ignore[arg-type]

        result = namespace.milestones("Website")

        assert result == [{"id": 3, "name": "Beta"}]
        assert "task_count" not in MILESTONE_FIELDS
        assert client.calls == [
            (
                "search_read",
                ("project.project",),
                {
                    "domain": [("name", "=ilike", "Website")],
                    "fields": ["id", "name"],
                    "order": "id",
                },
            ),
            (
                "search_read",
                ("project.milestone",),
                {
                    "domain": [("project_id", "=", 7)],
                    "fields": MILESTONE_FIELDS,
                    "order": "deadline, id",
                },
            ),
        ]

    def test_numeric_project_skips_name_lookup(self) -> None:
        client = _StubClient([[{"id": 3}]])
        namespace = ProjectNamespace(client=client)  # type: ignore[arg-type]

        namespace.milestones("7")

        assert len(client.calls) == 1
        assert client.calls[0][2]["domain"] == [("project_id", "=", 7)]

    def test_project_name_resolution_filters_ilike_wildcards_exactly(self) -> None:
        client = _StubClient([[{"id": 1, "name": "100XX"}, {"id": 2, "name": "100_% Complete"}]])
        namespace = ProjectNamespace(client=client)  # type: ignore[arg-type]

        assert namespace.resolve_project_id("100_% COMPLETE") == 2

    @pytest.mark.parametrize(
        "matches",
        [[], [{"id": 1, "name": "Website"}, {"id": 2, "name": "WEBSITE"}]],
    )
    def test_project_name_must_be_unique(self, matches: list[dict[str, Any]]) -> None:
        client = _StubClient([matches])
        namespace = ProjectNamespace(client=client)  # type: ignore[arg-type]

        with pytest.raises(VodooError):
            namespace.resolve_project_id("Website")

    def test_create_reach_and_list_tasks(self) -> None:
        client = _StubClient([[{"id": 5, "name": "Task"}]])
        namespace = ProjectNamespace(client=client)  # type: ignore[arg-type]

        assert namespace.create_milestone(7, "Beta", "2026-04-30") == 91
        assert namespace.reach_milestone(91) is True
        assert namespace.milestone_tasks(91) == [{"id": 5, "name": "Task"}]

        assert client.calls == [
            (
                "create",
                (
                    "project.milestone",
                    {"project_id": 7, "name": "Beta", "deadline": "2026-04-30"},
                ),
                {},
            ),
            ("write", ("project.milestone", [91], {"is_reached": True}), {}),
            (
                "search_read",
                ("project.task",),
                {
                    "domain": [("milestone_id", "=", 91)],
                    "fields": MILESTONE_TASK_FIELDS,
                    "order": "id",
                },
            ),
        ]

    def test_async_namespace_matches_sync_api(self) -> None:
        client = _StubAsyncClient([[{"id": 7, "name": "Website"}], [{"id": 3}], [{"id": 5}]])
        namespace = AsyncProjectNamespace(client=client)  # type: ignore[arg-type]

        async def exercise() -> None:
            assert await namespace.milestones("Website") == [{"id": 3}]
            assert await namespace.create_milestone(7, "Beta", "2026-04-30") == 91
            assert await namespace.reach_milestone(91) is True
            assert await namespace.milestone_tasks(91) == [{"id": 5}]

        asyncio.run(exercise())


class TestTaskMilestoneNamespace:
    def test_sync_and_async_set_milestone(self) -> None:
        records = [
            [{"id": 42, "project_id": [7, "Website"]}],
            [{"id": 91, "project_id": [7, "Website"]}],
        ]
        sync_client = _StubClient(read_results=records)
        sync_namespace = TaskNamespace(client=sync_client)  # type: ignore[arg-type]
        assert sync_namespace.set_milestone(42, 91) is True
        assert sync_client.calls == [
            ("read", ("project.task", [42]), {"fields": ["project_id"]}),
            ("read", ("project.milestone", [91]), {"fields": ["project_id"]}),
            ("write", ("project.task", [42], {"milestone_id": 91}), {}),
        ]

        async_client = _StubAsyncClient(read_results=records)
        async_namespace = AsyncTaskNamespace(client=async_client)  # type: ignore[arg-type]
        assert asyncio.run(async_namespace.set_milestone(42, 91)) is True
        assert async_client.calls == sync_client.calls

    @pytest.mark.parametrize(
        ("records", "error"),
        [
            ([[]], RecordNotFoundError),
            ([[{"project_id": [7, "Website"]}], []], RecordNotFoundError),
            (
                [
                    [{"project_id": [7, "Website"]}],
                    [{"project_id": [8, "Other"]}],
                ],
                RecordOperationError,
            ),
        ],
    )
    def test_set_milestone_rejects_missing_or_cross_project_records(
        self,
        records: list[list[dict[str, Any]]],
        error: type[Exception],
    ) -> None:
        sync_client = _StubClient(read_results=records)
        sync_namespace = TaskNamespace(client=sync_client)  # type: ignore[arg-type]
        with pytest.raises(error):
            sync_namespace.set_milestone(42, 91)
        assert all(call[0] != "write" for call in sync_client.calls)

        async_client = _StubAsyncClient(read_results=records)
        async_namespace = AsyncTaskNamespace(client=async_client)  # type: ignore[arg-type]
        with pytest.raises(error):
            asyncio.run(async_namespace.set_milestone(42, 91))
        assert all(call[0] != "write" for call in async_client.calls)


class _FakeProjects:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.reach_success = True

    def milestones(self, project: str) -> list[dict[str, Any]]:
        self.calls.append(("list", (project,)))
        return []

    def create_milestone(self, project: str, name: str, deadline: str) -> int:
        self.calls.append(("create", (project, name, deadline)))
        return 91

    def reach_milestone(self, milestone_id: int) -> bool:
        self.calls.append(("reach", (milestone_id,)))
        return self.reach_success

    def milestone_tasks(self, milestone_id: int) -> list[dict[str, Any]]:
        self.calls.append(("tasks", (milestone_id,)))
        return []


class _FakeTasks:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int]] = []
        self.set_success = True

    def set_milestone(self, task_id: int, milestone_id: int) -> bool:
        self.calls.append((task_id, milestone_id))
        return self.set_success


class _FakeCliClient:
    def __init__(self) -> None:
        self.projects = _FakeProjects()
        self.tasks = _FakeTasks()


class TestMilestoneCli:
    def test_all_milestone_commands_are_routed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _FakeCliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)
        runner = CliRunner()

        commands = [
            ["project", "milestone", "list", "--project", "Website"],
            [
                "project",
                "milestone",
                "create",
                "--project",
                "7",
                "--name",
                "Beta",
                "--deadline",
                "2026-04-30",
            ],
            ["project", "milestone", "reach", "91"],
            ["project", "milestone", "tasks", "91"],
            ["project-task", "milestone", "set", "42", "91"],
        ]
        for command in commands:
            result = runner.invoke(app, command)
            assert result.exit_code == 0, result.output

        assert client.projects.calls == [
            ("list", ("Website",)),
            ("create", ("7", "Beta", "2026-04-30")),
            ("reach", (91,)),
            ("tasks", (91,)),
        ]
        assert client.tasks.calls == [(42, 91)]

    def test_nested_group_supports_structured_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = _FakeCliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(
            app,
            ["project", "milestone", "--json", "list", "--project", "7"],
        )

        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == []

    @pytest.mark.parametrize(
        ("command", "configure_failure"),
        [
            (
                ["project", "milestone", "--json", "reach", "91"],
                lambda client: setattr(client.projects, "reach_success", False),
            ),
            (
                ["project-task", "milestone", "--json", "set", "42", "91"],
                lambda client: setattr(client.tasks, "set_success", False),
            ),
        ],
    )
    def test_mutation_false_result_is_one_structured_vodoo_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        command: list[str],
        configure_failure: Any,
    ) -> None:
        client = _FakeCliClient()
        configure_failure(client)
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(app, command)

        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["type"] == "vodoo_error"
        assert "Failed to" in payload["error"]
        assert result.output.count("\n") == 1

    @pytest.mark.parametrize("deadline", ["30-04-2026", "20260430", "2026-W18-4"])
    def test_create_rejects_invalid_deadline_before_connecting(
        self, monkeypatch: pytest.MonkeyPatch, deadline: str
    ) -> None:
        def fail_get_client() -> None:
            raise AssertionError("client should not be created")

        monkeypatch.setattr("vodoo.main.get_client", fail_get_client)
        result = CliRunner().invoke(
            app,
            [
                "project",
                "milestone",
                "create",
                "--project",
                "7",
                "--name",
                "Beta",
                "--deadline",
                deadline,
            ],
        )

        assert result.exit_code != 0
        assert "YYYY-MM-DD" in result.output
