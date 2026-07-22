"""Tests for activity domains, namespaces, and CLI commands."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from click import unstyle
from typer.testing import CliRunner

from vodoo import main as main_module
from vodoo.activities import ActivityNamespace, build_activity_domain
from vodoo.aio.activities import AsyncActivityNamespace
from vodoo.base import configure_output
from vodoo.exceptions import RecordNotFoundError, RecordOperationError
from vodoo.main import app


class _SyncClient:
    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = [{"id": 42, "active": True}] if records is None else records
        self.read_calls: list[tuple[str, list[int], list[str] | None]] = []
        self.calls: list[tuple[str, str, list[int]]] = []

    def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.read_calls.append((model, ids, fields))
        return self.records

    def execute(self, model: str, method: str, ids: list[int]) -> int:
        self.calls.append((model, method, ids))
        return 99


class _AsyncClient:
    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = [{"id": 42, "active": True}] if records is None else records
        self.read_calls: list[tuple[str, list[int], list[str] | None]] = []
        self.calls: list[tuple[str, str, list[int]]] = []

    async def read(
        self,
        model: str,
        ids: list[int],
        fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        self.read_calls.append((model, ids, fields))
        return self.records

    async def execute(self, model: str, method: str, ids: list[int]) -> int:
        self.calls.append((model, method, ids))
        return 99


class _CliActivities:
    def __init__(self) -> None:
        self.record = {
            "id": 7,
            "res_name": "Vendor Bill BILL/2025/001",
            "summary": "Upload invoice",
        }
        self.list_kwargs: dict[str, Any] | None = None
        self.get_calls: list[tuple[int, list[str] | None]] = []
        self.done_id: int | None = None

    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.list_kwargs = kwargs
        return []

    def get(self, activity_id: int, fields: list[str] | None = None) -> dict[str, Any]:
        self.get_calls.append((activity_id, fields))
        return self.record

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
        assert client.read_calls == [("mail.activity", [42], ["active"])]
        assert client.calls == [("mail.activity", "action_done", [42])]

    def test_done_rejects_missing_activity(self) -> None:
        client = _SyncClient(records=[])
        namespace = ActivityNamespace(client)  # type: ignore[arg-type]

        with pytest.raises(RecordNotFoundError):
            namespace.done(42)
        assert client.calls == []

    def test_done_rejects_inactive_activity(self) -> None:
        client = _SyncClient(records=[{"id": 42, "active": False}])
        namespace = ActivityNamespace(client)  # type: ignore[arg-type]

        with pytest.raises(RecordOperationError, match="already done"):
            namespace.done(42)
        assert client.calls == []

    def test_async_done_calls_odoo_action(self) -> None:
        client = _AsyncClient()
        namespace = AsyncActivityNamespace(client)  # type: ignore[arg-type]

        assert asyncio.run(namespace.done(42)) == 99
        assert client.read_calls == [("mail.activity", [42], ["active"])]
        assert client.calls == [("mail.activity", "action_done", [42])]

    def test_async_done_rejects_missing_activity(self) -> None:
        client = _AsyncClient(records=[])
        namespace = AsyncActivityNamespace(client)  # type: ignore[arg-type]

        with pytest.raises(RecordNotFoundError):
            asyncio.run(namespace.done(42))
        assert client.calls == []

    def test_async_done_rejects_inactive_activity(self) -> None:
        client = _AsyncClient(records=[{"id": 42, "active": False}])
        namespace = AsyncActivityNamespace(client)  # type: ignore[arg-type]

        with pytest.raises(RecordOperationError, match="already done"):
            asyncio.run(namespace.done(42))
        assert client.calls == []


class TestActivityCli:
    def teardown_method(self) -> None:
        main_module._console_config.update({"simple": False, "json": False, "toon": False})
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

    def test_show_default_fields_uses_generic_detail_output(self, monkeypatch: Any) -> None:
        client = _CliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(app, ["activity", "show", "7"])

        assert result.exit_code == 0
        assert client.activities.get_calls == [(7, None)]
        output = unstyle(result.output)
        assert "Activity #7" in output
        assert "Vendor Bill BILL/2025/001" in output
        assert "Upload invoice" in output

    def test_show_passes_custom_fields(self, monkeypatch: Any) -> None:
        client = _CliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(app, ["activity", "show", "7", "-f", "summary"])

        assert result.exit_code == 0
        assert client.activities.get_calls == [(7, ["summary"])]
        assert "Upload invoice" in result.output

    def test_show_outputs_structured_record(self, monkeypatch: Any) -> None:
        client = _CliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(app, ["--json", "activity", "show", "7"])

        assert result.exit_code == 0
        assert json.loads(result.output) == client.activities.record

    def test_done_calls_namespace(self, monkeypatch: Any) -> None:
        client = _CliClient()
        monkeypatch.setattr("vodoo.main.get_client", lambda: client)

        result = CliRunner().invoke(app, ["activity", "done", "42"])

        assert result.exit_code == 0
        assert client.activities.done_id == 42
        assert "Marked activity" in result.output
        assert "as done" in result.output
