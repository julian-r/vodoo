"""Tests for activity domains, namespaces, and CLI commands."""

from __future__ import annotations

import asyncio
from typing import Any

from typer.testing import CliRunner

from vodoo.activities import ActivityNamespace, build_activity_domain
from vodoo.aio.activities import AsyncActivityNamespace
from vodoo.base import configure_output
from vodoo.main import app


class _SyncClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[int]]] = []

    def execute(self, model: str, method: str, ids: list[int]) -> int:
        self.calls.append((model, method, ids))
        return 99


class _AsyncClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list[int]]] = []

    async def execute(self, model: str, method: str, ids: list[int]) -> int:
        self.calls.append((model, method, ids))
        return 99


class _CliActivities:
    def __init__(self) -> None:
        self.list_kwargs: dict[str, Any] | None = None
        self.done_id: int | None = None

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.list_kwargs = kwargs
        return []

    def done(self, activity_id: int) -> None:
        self.done_id = activity_id


class _CliClient:
    def __init__(self) -> None:
        self.activities = _CliActivities()


class TestActivityDomain:
    def test_empty_domain(self) -> None:
        assert build_activity_domain() == []

    def test_domain_with_all_filters(self) -> None:
        assert build_activity_domain(
            model="account.move",
            user="Alice",
            activity_type="To Do",
        ) == [
            ("res_model", "=", "account.move"),
            ("user_id.name", "ilike", "Alice"),
            ("activity_type_id.name", "ilike", "To Do"),
        ]


class TestActivityNamespace:
    def test_done_calls_odoo_action(self) -> None:
        client = _SyncClient()
        namespace = ActivityNamespace(client)  # type: ignore[arg-type]

        assert namespace.done(42) == 99
        assert client.calls == [("mail.activity", "action_done", [42])]

    def test_async_done_calls_odoo_action(self) -> None:
        client = _AsyncClient()
        namespace = AsyncActivityNamespace(client)  # type: ignore[arg-type]

        assert asyncio.run(namespace.done(42)) == 99
        assert client.calls == [("mail.activity", "action_done", [42])]


class TestActivityCli:
    def teardown_method(self) -> None:
        configure_output()

    def test_list_passes_filters_and_options(self, monkeypatch: Any) -> None:
        client = _CliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(
            app,
            [
                "activity",
                "list",
                "--model",
                "account.move",
                "--user",
                "Alice",
                "--type",
                "To Do",
                "--limit",
                "25",
                "-f",
                "id",
            ],
        )

        assert result.exit_code == 0
        assert client.activities.list_kwargs == {
            "domain": [
                ("res_model", "=", "account.move"),
                ("user_id.name", "ilike", "Alice"),
                ("activity_type_id.name", "ilike", "To Do"),
            ],
            "limit": 25,
            "fields": ["id"],
            "order": "date_deadline asc, id asc",
        }

    def test_done_calls_namespace(self, monkeypatch: Any) -> None:
        client = _CliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(app, ["activity", "done", "42"])

        assert result.exit_code == 0
        assert client.activities.done_id == 42
        assert "Marked activity" in result.output
        assert "as done" in result.output
