"""Tests for the fields_get helper on sync and async clients."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

from vodoo.aio.client import AsyncOdooClient
from vodoo.client import OdooClient

# ── Fixtures ──────────────────────────────────────────────────────────────────

FAKE_FIELDS: dict[str, Any] = {
    "name": {
        "type": "char",
        "string": "Name",
        "required": True,
        "readonly": False,
        "relation": "",
    },
    "partner_id": {
        "type": "many2one",
        "string": "Partner",
        "required": False,
        "readonly": False,
        "relation": "res.partner",
    },
    "active": {
        "type": "boolean",
        "string": "Active",
        "required": False,
        "readonly": False,
        "relation": "",
    },
}


def _make_sync_client() -> tuple[OdooClient, MagicMock]:
    """Create an OdooClient with a mocked transport."""
    transport = MagicMock()
    transport.execute_kw = MagicMock(return_value=FAKE_FIELDS)
    config = MagicMock()
    config.url = "http://localhost:8069"
    config.database = "test"
    config.username = "admin"
    config.password = "admin"
    config.retry_config = None
    client = OdooClient(config, transport=transport)
    return client, transport


def _make_async_client() -> tuple[AsyncOdooClient, MagicMock]:
    """Create an AsyncOdooClient with a mocked transport."""
    transport = MagicMock()
    transport.execute_kw = AsyncMock(return_value=FAKE_FIELDS)
    transport._uid = 2
    transport.close = AsyncMock()
    config = MagicMock()
    config.url = "http://localhost:8069"
    config.database = "test"
    config.username = "admin"
    config.password = "admin"
    config.retry_config = None
    client = AsyncOdooClient(config, transport=transport)
    return client, transport


# ── Sync client tests ────────────────────────────────────────────────────────


class TestSyncFieldsGet:
    def test_no_args_returns_all(self) -> None:
        client, transport = _make_sync_client()
        result = client.fields_get("res.partner")
        transport.execute_kw.assert_called_once_with("res.partner", "fields_get", [[]], None)
        assert result == FAKE_FIELDS

    def test_specific_fields(self) -> None:
        client, transport = _make_sync_client()
        client.fields_get("res.partner", fields=["name", "email"])
        transport.execute_kw.assert_called_once_with(
            "res.partner", "fields_get", [["name", "email"]], None
        )

    def test_specific_attributes(self) -> None:
        client, transport = _make_sync_client()
        client.fields_get("res.partner", attributes=["string", "type"])
        transport.execute_kw.assert_called_once_with(
            "res.partner",
            "fields_get",
            [[]],
            {"attributes": ["string", "type"]},
        )

    def test_fields_and_attributes(self) -> None:
        client, transport = _make_sync_client()
        client.fields_get("res.partner", fields=["name"], attributes=["string", "required"])
        transport.execute_kw.assert_called_once_with(
            "res.partner",
            "fields_get",
            [["name"]],
            {"attributes": ["string", "required"]},
        )


# ── Async client tests ───────────────────────────────────────────────────────


class TestAsyncFieldsGet:
    def test_no_args_returns_all(self) -> None:
        client, transport = _make_async_client()
        result = asyncio.run(client.fields_get("res.partner"))
        transport.execute_kw.assert_called_once_with("res.partner", "fields_get", [[]], None)
        assert result == FAKE_FIELDS

    def test_specific_fields(self) -> None:
        client, transport = _make_async_client()
        asyncio.run(client.fields_get("res.partner", fields=["name", "email"]))
        transport.execute_kw.assert_called_once_with(
            "res.partner", "fields_get", [["name", "email"]], None
        )

    def test_specific_attributes(self) -> None:
        client, transport = _make_async_client()
        asyncio.run(client.fields_get("res.partner", attributes=["string", "type"]))
        transport.execute_kw.assert_called_once_with(
            "res.partner",
            "fields_get",
            [[]],
            {"attributes": ["string", "type"]},
        )

    def test_fields_and_attributes(self) -> None:
        client, transport = _make_async_client()
        asyncio.run(
            client.fields_get("res.partner", fields=["name"], attributes=["string", "required"])
        )
        transport.execute_kw.assert_called_once_with(
            "res.partner",
            "fields_get",
            [["name"]],
            {"attributes": ["string", "required"]},
        )
