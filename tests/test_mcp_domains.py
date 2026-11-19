"""Unit tests for the MCP domain tools (tasks, helpdesk, CRM, documents, ...)."""

import base64
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client.client import Client

from tests.test_mcp_server import FakeClient, _call
from vodoo.mcp_server import create_server

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _domain(client: FakeClient, model: str) -> list[Any]:
    calls = [k for a, k in client.called("search_read") if a[0] == model]
    assert calls, f"no search_read on {model}"
    return list(calls[-1]["domain"])


async def test_list_tasks_filters() -> None:
    client = FakeClient()
    client.fields_result = {"state": {"type": "selection"}}
    is_error, data = await _call(
        client,
        "list_tasks",
        {
            "project": "Ops",
            "stage": "Doing",
            "mine": True,
            "tag": "bug",
            "deadline_before": "2026-12-01",
        },
    )
    assert not is_error, data
    domain = _domain(client, "project.task")
    assert ("project_id.name", "ilike", "Ops") in domain
    assert ("stage_id.name", "ilike", "Doing") in domain
    assert ("tag_ids.name", "ilike", "bug") in domain
    assert ("user_ids", "in", [2]) in domain
    assert ("date_deadline", "<", "2026-12-01") in domain
    assert ("state", "not in", ["1_done", "1_canceled"]) in domain


async def test_list_tasks_skips_state_filter_without_state_field() -> None:
    client = FakeClient()
    await _call(client, "list_tasks", {})
    assert _domain(client, "project.task") == []


async def test_list_tickets_search_and_open_only() -> None:
    client = FakeClient()
    client.fields_result = {"ticket_ref": {"type": "char"}}
    await _call(client, "list_tickets", {"search": "printer", "team": "Support"})
    domain = _domain(client, "helpdesk.ticket")
    assert ("team_id.name", "ilike", "Support") in domain
    assert domain.count("|") == 2
    assert ("ticket_ref", "ilike", "printer") in domain
    assert ("stage_id.fold", "=", False) in domain


async def test_list_leads_filters() -> None:
    client = FakeClient()
    await _call(client, "list_leads", {"lead_type": "opportunity", "salesperson": "Ann"})
    domain = _domain(client, "crm.lead")
    assert ("type", "=", "opportunity") in domain
    assert ("user_id.name", "ilike", "Ann") in domain


async def test_create_task_resolves_project_name() -> None:
    client = FakeClient()
    client.search_read_by_model["project.project"] = [{"id": 7, "name": "Ops"}]
    is_error, data = await _call(
        client,
        "create_task",
        {
            "name": "Fix printer",
            "project": "Ops",
            "description": "**Now**",
            "assignee_ids": [5],
            "deadline": "2026-12-01",
        },
        allow_write=True,
    )
    assert not is_error, data
    (args, kwargs) = next((a, k) for a, k in client.called("create") if a[0] == "project.task")
    values = args[1]
    assert values["project_id"] == 7
    assert values["description"] == "**Now**"  # Markdown, converted by the real client
    assert values["user_ids"] == [(6, 0, [5])]
    assert values["date_deadline"] == "2026-12-01"
    assert kwargs["context"] == {"default_project_id": 7}
    assert data["id"] == 101


async def test_create_task_extra_values_cannot_delete() -> None:
    client = FakeClient()
    is_error, text = await _call(
        client,
        "create_task",
        {"name": "x", "project": 7, "extra_values": {"child_ids": [[2, 3, 0]]}},
        allow_write=True,
    )
    assert is_error
    assert "--allow-delete" in text
    assert not client.called("create")


async def test_create_ticket_and_lead_values() -> None:
    client = FakeClient()
    await _call(
        client,
        "create_ticket",
        {"name": "Down", "description": "It *broke*", "priority": "3", "assignee_id": 4},
        allow_write=True,
    )
    values = next(a[1] for a, _ in client.called("create") if a[0] == "helpdesk.ticket")
    assert values == {"name": "Down", "description": "It *broke*", "priority": "3", "user_id": 4}

    await _call(
        client,
        "create_lead",
        {"name": "Big deal", "expected_revenue": 5000, "email": "a@b.c", "tag_ids": [1]},
        allow_write=True,
    )
    values = next(a[1] for a, _ in client.called("create") if a[0] == "crm.lead")
    assert values["type"] == "opportunity"
    assert values["expected_revenue"] == 5000
    assert values["email_from"] == "a@b.c"
    assert values["tag_ids"] == [(6, 0, [1])]


async def test_add_tag_links_without_replacing() -> None:
    client = FakeClient()
    await _call(client, "add_tag", {"kind": "lead", "record_id": 3, "tag_id": 9}, allow_write=True)
    (args, _) = client.called("write")[0]
    assert args == ("crm.lead", [3], {"tag_ids": [(4, 9, 0)]})


async def test_schedule_activity_defaults_to_todo_for_me() -> None:
    client = FakeClient()
    client.search_read_by_model["ir.model"] = [{"id": 77}]
    client.execute_result["check_object_reference"] = ["mail.activity.type", 4]
    is_error, data = await _call(
        client,
        "schedule_activity",
        {"model": "account.move", "record_id": 12, "summary": "Chase", "deadline": "2026-12-01"},
        allow_write=True,
    )
    assert not is_error, data
    values = next(a[1] for a, _ in client.called("create") if a[0] == "mail.activity")
    assert values == {
        "res_model_id": 77,
        "res_id": 12,
        "summary": "Chase",
        "date_deadline": "2026-12-01",
        "user_id": 2,
        "activity_type_id": 4,
    }


async def test_crm_pipeline_hides_deals_by_default() -> None:
    client = FakeClient()
    client.search_read_by_model["crm.stage"] = [{"id": 1, "name": "New", "sequence": 1}]
    client.search_read_by_model["crm.lead"] = [
        {"id": 5, "name": "D", "stage_id": [1, "New"], "expected_revenue": 10, "probability": 50}
    ]
    _, data = await _call(client, "crm_pipeline", {"health": False})
    assert "deals" not in data
    assert data["stages"][0]["deals"] == 1  # per-stage count stays
    _, data = await _call(client, "crm_pipeline", {"health": False, "include_deals": True})
    assert [d["id"] for d in data["deals"]] == [5]


async def test_download_document_into_download_dir(tmp_path: Path) -> None:
    client = FakeClient()
    client.read_result["documents.document"] = [
        {
            "id": 4,
            "name": "contract.pdf",
            "type": "binary",
            "datas": base64.b64encode(b"%PDF").decode(),
        }
    ]
    _, data = await _call(client, "download_document", {"document_id": 4}, download_dir=tmp_path)
    assert Path(data["path"]).read_bytes() == b"%PDF"
    is_error, _ = await _call(
        client, "download_document", {"document_id": 4, "output_dir": "/etc"}, download_dir=tmp_path
    )
    assert is_error


async def test_upload_document_only_from_allowed_folders(tmp_path: Path) -> None:
    client = FakeClient()
    outside = tmp_path / "outside.pdf"
    outside.write_bytes(b"x")
    is_error, text = await _call(
        client,
        "upload_document",
        {"file_path": str(outside), "folder": 3},
        allow_write=True,
        upload_dirs=[tmp_path / "allowed"],
        download_dir=tmp_path / "dl",
    )
    assert is_error
    assert "Can only attach" in text
    assert not client.called("create")


# ── Hiding tools for apps that are not installed ──────────────────────────


async def _visible_tools(client: FakeClient, **kw: Any) -> tuple[set[str], dict[str, Any]]:
    server = create_server(client=client, allow_write=True, **kw)  # type: ignore[arg-type]
    async with Client(server) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        info = json.loads((await session.call_tool("odoo_info", {})).content[0].text)
    return names, info


async def test_hides_tools_of_missing_apps() -> None:
    client = FakeClient()
    client.read_result["res.users"] = [{"name": "Me"}]
    client.search_read_by_model["ir.model"] = [
        {"model": m}
        for m in ("res.partner", "project.task", "project.project", "project.task.type")
    ]
    names, info = await _visible_tools(client)
    assert "list_tasks" in names
    assert "create_task" in names
    assert "search_records" in names
    for missing in (
        "list_tickets",
        "create_ticket",
        "list_articles",
        "list_account_moves",
        "timer_start",
    ):
        assert missing not in names
        assert missing in info["hidden_tools"]


async def test_keeps_all_tools_when_check_is_unusable() -> None:
    client = FakeClient()  # ir.model answers nothing (not even res.partner)
    client.read_result["res.users"] = [{"name": "Me"}]
    names, info = await _visible_tools(client)
    assert {"list_tickets", "list_tasks", "register_payment"} <= names
    assert info["hidden_tools"] == []


async def test_create_article_uses_article_create_for_privacy() -> None:
    client = FakeClient()
    client.execute_result["article_create"] = [55]  # Odoo 19 returns a list
    client.read_result["knowledge.article"] = [{"id": 55, "category": "private"}]
    is_error, data = await _call(
        client,
        "create_article",
        {"name": "Salaries", "body": "**secret**", "private": True},
        allow_write=True,
    )
    assert not is_error, data
    (_, kwargs) = next((a, k) for a, k in client.called("execute") if a[1] == "article_create")
    assert kwargs == {"title": "Salaries", "is_private": True}
    assert not [a for a, _ in client.called("create") if a[0] == "knowledge.article"]
    (write_args, _) = client.called("write")[0]
    assert write_args[:2] == ("knowledge.article", [55])
    assert write_args[2] == {"body": "**secret**"}
    assert data["category"] == "private"


async def test_activity_type_is_limited_to_the_model_and_unique() -> None:
    client = FakeClient()
    client.search_read_by_model["ir.model"] = [{"id": 77}]
    client.search_read_by_model["mail.activity.type"] = [
        {"id": 3, "name": "Call"},
        {"id": 9, "name": "Call"},
    ]
    is_error, text = await _call(
        client,
        "schedule_activity",
        {
            "model": "crm.lead",
            "record_id": 1,
            "summary": "x",
            "deadline": "2026-12-01",
            "activity_type": "Call",
        },
        allow_write=True,
    )
    assert is_error
    assert "ambiguous" in text
    domain = _domain(client, "mail.activity.type")
    assert domain[:3] == ["|", ("res_model", "=", False), ("res_model", "=", "crm.lead")]
    assert not [a for a, _ in client.called("create") if a[0] == "mail.activity"]


async def test_keeps_all_tools_when_ir_model_is_denied() -> None:
    from vodoo.exceptions import OdooAccessError

    class DeniedIrModel(FakeClient):
        async def search_read(self, model: str, **kwargs: Any) -> list[dict[str, Any]]:
            if model == "ir.model":
                raise OdooAccessError("You are not allowed to access 'Models' (ir.model)")
            return await super().search_read(model, **kwargs)

    client = DeniedIrModel()
    client.read_result["res.users"] = [{"name": "Me"}]
    names, info = await _visible_tools(client)
    assert {"list_tickets", "list_articles", "register_payment"} <= names
    assert info["hidden_tools"] == []


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("create_ticket", {"name": "x", "extra_values": {"sla_ids": [[2, 1, 0]]}}),
        ("create_lead", {"name": "x", "extra_values": {"order_ids": [[2.0, 1]]}}),
        (
            "create_lead",
            {"name": "x", "extra_values": {"order_ids": [[0, 0, {"line_ids": [[2, 4]]}]]}},
        ),
    ],
)
async def test_domain_create_tools_cannot_delete(tool: str, args: dict[str, Any]) -> None:
    client = FakeClient()
    is_error, text = await _call(client, tool, args, allow_write=True)
    assert is_error
    assert "--allow-delete" in text
    assert not client.called("create")
    client = FakeClient()
    is_error, _ = await _call(client, tool, args, allow_write=True, allow_delete=True)
    assert not is_error


@pytest.mark.parametrize(
    ("tool", "args", "hint"),
    [
        ("create_ticket", {"name": "x", "extra_values": {"tag_ids": [[6, 0, [1]]]}}, "'tag_ids'"),
        ("create_lead", {"name": "x", "extra_values": {"user_id": 3}}, "'salesperson_id'"),
        (
            "create_task",
            {"name": "x", "project": 1, "extra_values": {"user_ids": []}},
            "'assignee_ids'",
        ),
    ],
)
async def test_extra_values_cannot_shadow_parameters(
    tool: str, args: dict[str, Any], hint: str
) -> None:
    client = FakeClient()
    is_error, text = await _call(client, tool, args, allow_write=True)
    assert is_error
    assert hint in text
    assert not client.called("create")
