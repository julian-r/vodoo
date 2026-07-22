"""Tests for project task dependency and scheduling operations."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from vodoo.aio.project_tasks import AsyncTaskNamespace
from vodoo.main import app
from vodoo.project_tasks import TaskNamespace


class _StubClient:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[str, list[int], dict[str, Any]]] = []

    def write(self, model: str, record_ids: list[int], values: dict[str, Any]) -> bool:
        self.calls.append((model, record_ids, values))
        return self.result


class _StubAsyncClient:
    def __init__(self, result: bool = True) -> None:
        self.result = result
        self.calls: list[tuple[str, list[int], dict[str, Any]]] = []

    async def write(self, model: str, record_ids: list[int], values: dict[str, Any]) -> bool:
        self.calls.append((model, record_ids, values))
        return self.result


class TestTaskNamespacePlanning:
    def test_add_dependencies_preserves_existing_links(self) -> None:
        client = _StubClient()
        namespace = TaskNamespace(client=client)  # type: ignore[arg-type]

        assert namespace.add_dependencies(42, [10, 11]) is True
        assert client.calls == [("project.task", [42], {"depend_on_ids": [(4, 10, 0), (4, 11, 0)]})]

    def test_clear_dependencies(self) -> None:
        client = _StubClient()
        namespace = TaskNamespace(client=client)  # type: ignore[arg-type]

        assert namespace.clear_dependencies(42) is True
        assert client.calls == [("project.task", [42], {"depend_on_ids": [(5, 0, 0)]})]

    def test_schedule_sets_start_and_deadline(self) -> None:
        client = _StubClient(result=False)
        namespace = TaskNamespace(client=client)  # type: ignore[arg-type]

        assert namespace.schedule(42, "2026-04-01 09:00:00", "2026-04-03") is False
        assert client.calls == [
            (
                "project.task",
                [42],
                {
                    "planned_date_begin": "2026-04-01 09:00:00",
                    "date_deadline": "2026-04-03",
                },
            )
        ]

    @pytest.mark.parametrize("start", ["2026-4-01 09:00:00", "2026-04-01 09:00:60"])
    def test_schedule_rejects_invalid_formats_before_writing(self, start: str) -> None:
        client = _StubClient()
        namespace = TaskNamespace(client=client)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="start must use YYYY-MM-DD HH:MM:SS format"):
            namespace.schedule(42, start, "2026-04-03")

        assert client.calls == []

    def test_async_operations_match_sync_payloads(self) -> None:
        client = _StubAsyncClient()
        namespace = AsyncTaskNamespace(client=client)  # type: ignore[arg-type]

        async def run_operations() -> None:
            assert await namespace.add_dependencies(42, [10, 11]) is True
            assert await namespace.clear_dependencies(42) is True
            assert await namespace.schedule(42, "2026-04-01 09:00:00", "2026-04-03") is True

        asyncio.run(run_operations())

        assert client.calls == [
            ("project.task", [42], {"depend_on_ids": [(4, 10, 0), (4, 11, 0)]}),
            ("project.task", [42], {"depend_on_ids": [(5, 0, 0)]}),
            (
                "project.task",
                [42],
                {
                    "planned_date_begin": "2026-04-01 09:00:00",
                    "date_deadline": "2026-04-03",
                },
            ),
        ]

    def test_async_schedule_rejects_invalid_formats_before_writing(self) -> None:
        client = _StubAsyncClient()
        namespace = AsyncTaskNamespace(client=client)  # type: ignore[arg-type]

        with pytest.raises(ValueError, match="end must use YYYY-MM-DD format"):
            asyncio.run(namespace.schedule(42, "2026-04-01 09:00:00", "2026-04-31"))

        assert client.calls == []


class TestProjectTaskPlanningCli:
    def setup_method(self) -> None:
        self.runner = CliRunner()
        self.tasks = MagicMock()
        self.tasks.add_dependencies.return_value = True
        self.tasks.clear_dependencies.return_value = True
        self.tasks.schedule.return_value = True
        self.client = MagicMock(tasks=self.tasks)

    def test_depends_add_routes_all_blocker_ids(self) -> None:
        with patch("vodoo.main.get_client", return_value=self.client):
            result = self.runner.invoke(
                app, ["project-task", "--simple", "depends", "add", "42", "10", "11"]
            )

        assert result.exit_code == 0
        self.tasks.add_dependencies.assert_called_once_with(42, [10, 11])
        assert "Successfully added dependencies 10, 11 to task 42" in result.output

    def test_depends_add_requires_a_blocker_id(self) -> None:
        with patch("vodoo.main.get_client", return_value=self.client):
            result = self.runner.invoke(app, ["project-task", "--simple", "depends", "add", "42"])

        assert result.exit_code != 0
        self.tasks.add_dependencies.assert_not_called()

    def test_depends_clear_routes_task_id(self) -> None:
        with patch("vodoo.main.get_client", return_value=self.client):
            result = self.runner.invoke(app, ["project-task", "--simple", "depends", "clear", "42"])

        assert result.exit_code == 0
        self.tasks.clear_dependencies.assert_called_once_with(42)
        assert "Successfully cleared dependencies from task 42" in result.output

    def test_schedule_routes_dates(self) -> None:
        with patch("vodoo.main.get_client", return_value=self.client):
            result = self.runner.invoke(
                app,
                [
                    "project-task",
                    "--simple",
                    "schedule",
                    "42",
                    "--start",
                    "2026-04-01 09:00:00",
                    "--end",
                    "2026-04-03",
                ],
            )

        assert result.exit_code == 0
        self.tasks.schedule.assert_called_once_with(42, "2026-04-01 09:00:00", "2026-04-03")
        assert "Successfully scheduled task 42" in result.output

    @pytest.mark.parametrize(
        ("method", "arguments", "action"),
        [
            ("add_dependencies", ["depends", "add", "42", "10"], "depends_add"),
            ("clear_dependencies", ["depends", "clear", "42"], "depends_clear"),
            (
                "schedule",
                [
                    "schedule",
                    "42",
                    "--start",
                    "2026-04-01 09:00:00",
                    "--end",
                    "2026-04-03",
                ],
                "schedule",
            ),
        ],
    )
    @pytest.mark.parametrize("output_mode", ["--json", "--toon"])
    def test_failed_writes_use_structured_output(
        self,
        method: str,
        arguments: list[str],
        action: str,
        output_mode: str,
    ) -> None:
        getattr(self.tasks, method).return_value = False
        with patch("vodoo.main.get_client", return_value=self.client):
            result = self.runner.invoke(app, ["project-task", output_mode, *arguments])

        assert result.exit_code == 1
        assert "\x1b[" not in result.output
        if output_mode == "--json":
            assert json.loads(result.output) == {"ok": False, "id": 42, "action": action}
        else:
            assert result.output == f"ok: false\nid: 42\naction: {action}\n"

    @pytest.mark.parametrize(
        ("start", "end", "error"),
        [
            ("2026-4-01 09:00:00", "2026-04-03", "start must use YYYY-MM-DD HH:MM:SS"),
            ("2026-04-01 09:00:00", "2026-04-31", "end must use YYYY-MM-DD"),
        ],
    )
    def test_schedule_rejects_malformed_dates_before_rpc(
        self, start: str, end: str, error: str
    ) -> None:
        get_client = MagicMock(return_value=self.client)
        with patch("vodoo.main.get_client", get_client):
            result = self.runner.invoke(
                app,
                [
                    "project-task",
                    "--simple",
                    "schedule",
                    "42",
                    "--start",
                    start,
                    "--end",
                    end,
                ],
            )

        assert result.exit_code == 2
        assert error in result.output
        get_client.assert_not_called()

    @pytest.mark.parametrize("output_mode", ["--json", "--toon"])
    def test_schedule_validation_errors_use_structured_output(self, output_mode: str) -> None:
        get_client = MagicMock(return_value=self.client)
        with patch("vodoo.main.get_client", get_client):
            result = self.runner.invoke(
                app,
                [
                    "project-task",
                    output_mode,
                    "schedule",
                    "42",
                    "--start",
                    "2026-4-01 09:00:00",
                    "--end",
                    "2026-04-03",
                ],
            )

        assert result.exit_code == 2
        assert "\x1b[" not in result.output
        if output_mode == "--json":
            assert json.loads(result.output) == {
                "error": "start must use YYYY-MM-DD HH:MM:SS format",
                "type": "validation",
            }
        else:
            assert result.output == (
                'error: "start must use YYYY-MM-DD HH:MM:SS format"\ntype: validation\n'
            )
        get_client.assert_not_called()

    def test_failed_write_exits_nonzero(self) -> None:
        self.tasks.schedule.return_value = False
        with patch("vodoo.main.get_client", return_value=self.client):
            result = self.runner.invoke(
                app,
                [
                    "project-task",
                    "--simple",
                    "schedule",
                    "42",
                    "--start",
                    "2026-04-01 09:00:00",
                    "--end",
                    "2026-04-03",
                ],
            )

        assert result.exit_code == 1
        assert "Failed to schedule task 42" in result.output
