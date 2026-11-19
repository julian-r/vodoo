"""MCP server integration tests against a live Odoo (17, 18, 19).

Drives the server through the MCP protocol (in-memory client) and exercises a full
accounting cycle: invoice → post → pay, reset/cancel, journal entry, chatter,
attachments, generic method calls, and deletion.
"""

import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client.client import Client

from vodoo.aio.client import AsyncOdooClient
from vodoo.config import OdooConfig
from vodoo.mcp_server import create_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def mcp(odoo_config: OdooConfig, tmp_path: Path) -> AsyncIterator["_Mcp"]:
    async with AsyncOdooClient(odoo_config) as odoo:
        server = create_server(
            client=odoo,
            allow_write=True,
            allow_delete=True,
            download_dir=tmp_path / "downloads",
            upload_dirs=[tmp_path],
        )
        async with Client(server) as session:
            yield _Mcp(session)


class _Mcp:
    def __init__(self, session: Client) -> None:
        self.session = session

    async def call(self, tool: str, **args: Any) -> Any:
        result = await self.session.call_tool(tool, args)
        text = result.content[0].text
        assert not result.is_error, f"{tool} failed: {text}"
        return json.loads(text)

    async def error(self, tool: str, **args: Any) -> str:
        result = await self.session.call_tool(tool, args)
        assert result.is_error, f"{tool} unexpectedly succeeded"
        return str(result.content[0].text)


async def _partner(mcp: _Mcp, suffix: str) -> int:
    created = await mcp.call(
        "create_record",
        model="res.partner",
        values={"name": f"Vodoo MCP Customer {suffix}", "email": f"mcp-{suffix}@example.com"},
    )
    return int(created["id"])


async def _account_id(mcp: _Mcp, account_type: str) -> int:
    found = await mcp.call(
        "search_records",
        model="account.account",
        domain=[["account_type", "=", account_type]],
        fields=["id", "code", "name"],
        limit=1,
    )
    if not found["records"]:
        pytest.skip(f"No {account_type} account (chart of accounts not installed?)")
    return int(found["records"][0]["id"])


async def test_info_reports_connection_and_modes(mcp: _Mcp) -> None:
    info = await mcp.call("odoo_info")
    assert info["user"]["id"] > 0
    assert info["write_enabled"] is True
    assert info["delete_enabled"] is True


async def test_fields_and_name_search(mcp: _Mcp) -> None:
    fields = await mcp.call("get_fields", model="account.move", field_names=["move_type", "state"])
    assert fields["move_type"]["type"] == "selection"
    suffix = str(time.time_ns())
    partner_id = await _partner(mcp, suffix)
    matches = await mcp.call("name_search", model="res.partner", name=f"Customer {suffix}")
    assert [m["id"] for m in matches] == [partner_id]


async def test_invoice_post_and_pay(mcp: _Mcp) -> None:
    suffix = str(time.time_ns())
    partner_id = await _partner(mcp, suffix)

    invoice = await mcp.call(
        "create_account_move",
        move_type="out_invoice",
        partner_id=partner_id,
        invoice_date="2026-01-15",
        ref=f"MCP-{suffix}",
        narration="Thanks for your **business**",
        lines=[
            {"name": "Consulting", "quantity": 2, "price_unit": 150, "tax_ids": []},
            {"name": "Travel", "quantity": 1, "price_unit": 50, "tax_ids": []},
        ],
    )
    move_id = invoice["id"]
    assert invoice["state"] == "draft"
    assert invoice["amount_total"] == pytest.approx(350.0)
    assert [line["name"] for line in invoice["lines"]] == ["Consulting", "Travel"]
    assert invoice["url"].startswith("http")

    posted = await mcp.call("post_account_moves", move_ids=[move_id])
    assert posted[0]["state"] == "posted"
    assert posted[0]["name"] not in ("/", False, None)
    assert posted[0]["payment_state"] == "not_paid"

    listed = await mcp.call(
        "list_account_moves", move_type="out_invoice", partner=f"Customer {suffix}"
    )
    assert [r["id"] for r in listed["records"]] == [move_id]
    unpaid = await mcp.call("list_account_moves", search=f"MCP-{suffix}", payment_state="not_paid")
    assert unpaid["total"] == 1

    paid = await mcp.call(
        "register_payment", move_ids=[move_id], payment_date="2026-01-20", memo=f"Pay {suffix}"
    )
    assert paid["moves"][0]["payment_state"] in ("paid", "in_payment")
    assert paid["moves"][0]["amount_residual"] == pytest.approx(0.0)
    assert len(paid["payments"]) == 1
    assert paid["payments"][0]["amount"] == pytest.approx(350.0)


async def test_partial_payment(mcp: _Mcp) -> None:
    partner_id = await _partner(mcp, str(time.time_ns()))
    bill = await mcp.call(
        "create_account_move",
        move_type="in_invoice",
        partner_id=partner_id,
        invoice_date="2026-02-01",
        lines=[{"name": "Hosting", "quantity": 1, "price_unit": 200, "tax_ids": []}],
        post=True,
    )
    assert bill["state"] == "posted"
    paid = await mcp.call("register_payment", move_ids=[bill["id"]], amount=80)
    assert paid["moves"][0]["payment_state"] == "partial"
    assert paid["moves"][0]["amount_residual"] == pytest.approx(120.0)


async def test_reset_to_draft_and_cancel(mcp: _Mcp) -> None:
    partner_id = await _partner(mcp, str(time.time_ns()))
    invoice = await mcp.call(
        "create_account_move",
        move_type="out_invoice",
        partner_id=partner_id,
        lines=[{"name": "Workshop", "quantity": 1, "price_unit": 100, "tax_ids": []}],
        post=True,
    )
    move_id = invoice["id"]
    draft = await mcp.call("reset_account_moves_to_draft", move_ids=[move_id])
    assert draft[0]["state"] == "draft"

    await mcp.call(
        "update_records",
        model="account.move",
        ids=[move_id],
        values={"invoice_line_ids": [[1, invoice["lines"][0]["id"], {"price_unit": 120}]]},
    )
    updated = await mcp.call("get_account_move", move_id=move_id)
    assert updated["amount_total"] == pytest.approx(120.0)

    cancelled = await mcp.call("cancel_account_moves", move_ids=[move_id])
    assert cancelled[0]["state"] == "cancel"

    # Paying a cancelled invoice is refused (Odoo 18's wizard would create a payment).
    message = await mcp.error("register_payment", move_ids=[move_id])
    assert "must be posted" in message

    # Odoo's own validation errors reach the model as readable tool errors.
    message = await mcp.error("post_account_moves", move_ids=[move_id])
    assert "Error" in message


async def test_journal_entry_via_call_method(mcp: _Mcp) -> None:
    income = await _account_id(mcp, "income")
    receivable = await _account_id(mcp, "asset_receivable")
    entry = await mcp.call(
        "create_account_move",
        move_type="entry",
        date="2026-03-31",
        ref="Vodoo MCP accrual",
        lines=[
            {"name": "Accrual", "account_id": receivable, "debit": 75},
            {"name": "Accrual", "account_id": income, "credit": 75},
        ],
    )
    assert entry["state"] == "draft"
    assert sorted((line["debit"], line["credit"]) for line in entry["lines"]) == [
        (0.0, 75.0),
        (75.0, 0.0),
    ]
    await mcp.call("call_method", model="account.move", method="action_post", ids=[entry["id"]])
    posted = await mcp.call("read_records", model="account.move", ids=[entry["id"]])
    assert posted[0]["state"] == "posted"


async def test_chatter_and_attachments(mcp: _Mcp, tmp_path: Path) -> None:
    partner_id = await _partner(mcp, str(time.time_ns()))
    invoice = await mcp.call(
        "create_account_move",
        move_type="out_invoice",
        partner_id=partner_id,
        lines=[{"name": "Support", "quantity": 1, "price_unit": 10, "tax_ids": []}],
    )
    move_id = invoice["id"]

    posted = await mcp.call(
        "post_message", model="account.move", record_id=move_id, message="Checked by **MCP**"
    )
    assert posted["internal"] is True
    messages = await mcp.call("list_messages", model="account.move", record_id=move_id)
    assert any("Checked by **MCP**" in (m.get("body") or "") for m in messages)

    source = tmp_path / "receipt.txt"
    source.write_bytes(b"receipt 42")
    attached = await mcp.call(
        "attach_file", model="account.move", record_id=move_id, file_path=str(source)
    )
    attachments = await mcp.call("list_attachments", model="account.move", record_id=move_id)
    assert attached["attachment_id"] in [a["id"] for a in attachments]

    downloaded = await mcp.call(
        "download_attachment", attachment_id=attached["attachment_id"], output_dir="invoices"
    )
    path = Path(downloaded["path"])
    assert path.parent == (tmp_path / "downloads" / "invoices").resolve()
    assert path.read_bytes() == b"receipt 42"


async def test_delete_records(mcp: _Mcp) -> None:
    partner_id = await _partner(mcp, str(time.time_ns()))
    deleted = await mcp.call("delete_records", model="res.partner", ids=[partner_id])
    assert deleted["ok"] is True
    remaining = await mcp.call(
        "count_records", model="res.partner", domain=[["id", "=", partner_id]]
    )
    assert remaining["count"] == 0
