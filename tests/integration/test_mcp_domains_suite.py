"""MCP domain tools against a live Odoo (17, 18, 19; community and enterprise).

Community: projects, tasks, milestones, dependencies, tags, CRM, activities.
Enterprise adds helpdesk, knowledge, and documents. On community those tools
must be hidden (the server checks which apps are installed).
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

ENTERPRISE_TOOLS = {
    "list_tickets",
    "create_ticket",
    "list_articles",
    "create_article",
    "list_documents",
    "list_document_folders",
    "download_document",
    "upload_document",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _Mcp:
    def __init__(self, session: Client, tools: set[str]) -> None:
        self.session = session
        self.tools = tools

    async def call(self, tool: str, **args: Any) -> Any:
        result = await self.session.call_tool(tool, args)
        text = result.content[0].text
        assert not result.is_error, f"{tool} failed: {text}"
        return json.loads(text)

    def require(self, tool: str) -> None:
        if tool not in self.tools:
            pytest.skip(f"{tool} is hidden: its Odoo app is not installed")


@pytest.fixture
async def mcp(odoo_config: OdooConfig, tmp_path: Path) -> AsyncIterator[_Mcp]:
    async with AsyncOdooClient(odoo_config) as odoo:
        server = create_server(
            client=odoo,
            allow_write=True,
            download_dir=tmp_path / "downloads",
            upload_dirs=[tmp_path],
        )
        async with Client(server) as session:
            tools = {t.name for t in (await session.list_tools()).tools}
            yield _Mcp(session, tools)


def _suffix() -> str:
    return str(time.time_ns())


async def test_tools_match_installed_apps(mcp: _Mcp, is_enterprise: bool) -> None:
    info = await mcp.call("odoo_info")
    assert {"list_tasks", "create_task", "list_leads", "list_account_moves"} <= mcp.tools
    if is_enterprise:
        assert {"list_tickets", "list_articles", "list_documents"} <= mcp.tools
    else:
        assert ENTERPRISE_TOOLS.isdisjoint(mcp.tools)
        assert set(info["hidden_tools"]) >= ENTERPRISE_TOOLS


async def test_project_task_workflow(mcp: _Mcp, is_enterprise: bool) -> None:
    suffix = _suffix()
    project = await mcp.call(
        "create_record", model="project.project", values={"name": f"MCP Project {suffix}"}
    )
    project_id = project["id"]
    stage = await mcp.call(
        "create_record",
        model="project.task.type",
        values={"name": f"MCP Doing {suffix}", "project_ids": [[6, 0, [project_id]]]},
    )
    stages = await mcp.call("list_project_stages", project_id=project_id)
    assert stage["id"] in [s["id"] for s in stages]

    listed = await mcp.call("list_projects", name=f"MCP Project {suffix}")
    assert [p["id"] for p in listed["records"]] == [project_id]

    milestone = await mcp.call(
        "create_milestone", project=f"MCP Project {suffix}", name="Beta", deadline="2026-12-31"
    )
    blocker = await mcp.call("create_task", name=f"Blocker {suffix}", project=project_id)
    task = await mcp.call(
        "create_task",
        name=f"Main {suffix}",
        project=f"MCP Project {suffix}",
        description="Needs **care**",
        stage_id=stage["id"],
        deadline="2026-12-15",
        priority="1",
    )
    subtask = await mcp.call(
        "create_task", name=f"Sub {suffix}", project=project_id, parent_id=task["id"]
    )

    await mcp.call("set_task_milestone", task_id=task["id"], milestone_id=milestone["id"])
    deps = await mcp.call("set_task_dependencies", task_id=task["id"], add_ids=[blocker["id"]])
    assert deps["depend_on_ids"] == [blocker["id"]]

    tag = await mcp.call("create_tag", kind="task", name=f"mcp-{suffix}")
    await mcp.call("add_tag", kind="task", record_id=task["id"], tag_id=tag["id"])
    assert tag["id"] in [t["id"] for t in await mcp.call("list_tags", kind="task")]

    by_tag = await mcp.call("list_tasks", project=f"MCP Project {suffix}", tag=f"mcp-{suffix}")
    assert [t["id"] for t in by_tag["records"]] == [task["id"]]
    in_stage = await mcp.call("list_tasks", project=f"MCP Project {suffix}", stage="MCP Doing")
    assert task["id"] in [t["id"] for t in in_stage["records"]]
    subtasks = await mcp.call("list_tasks", parent_id=task["id"])
    assert [t["id"] for t in subtasks["records"]] == [subtask["id"]]

    # Odoo copies the milestone to subtasks of the same project.
    milestone_tasks = await mcp.call("list_milestone_tasks", milestone_id=milestone["id"])
    assert task["id"] in [t["id"] for t in milestone_tasks]
    assert blocker["id"] not in [t["id"] for t in milestone_tasks]
    await mcp.call("reach_milestone", milestone_id=milestone["id"])
    milestones = await mcp.call("list_milestones", project=project_id)
    assert milestones[0]["is_reached"] is True

    context = await mcp.call("get_task_context", task_id=task["id"])
    text = json.dumps(context)
    assert f"Main {suffix}" in text
    assert f"Blocker {suffix}" in text

    cleared = await mcp.call("set_task_dependencies", task_id=task["id"], clear=True)
    assert cleared["depend_on_ids"] == []

    if is_enterprise:  # Gantt dates need Project Enterprise
        await mcp.call(
            "schedule_task", task_id=task["id"], start="2026-12-01 08:00:00", end="2026-12-05"
        )
        rows = await mcp.call(
            "read_records",
            model="project.task",
            ids=[task["id"]],
            fields=["planned_date_begin", "date_deadline"],
        )
        assert rows[0]["planned_date_begin"].startswith("2026-12-01")
        assert rows[0]["date_deadline"].startswith("2026-12-05")


async def test_crm_workflow(mcp: _Mcp) -> None:
    suffix = _suffix()
    stages = await mcp.call("list_crm_stages")
    assert stages
    lead = await mcp.call(
        "create_lead",
        name=f"MCP Deal {suffix}",
        expected_revenue=12000,
        probability=40,
        email=f"deal-{suffix}@example.com",
        stage_id=stages[0]["id"],
    )
    found = await mcp.call("list_leads", search=f"deal-{suffix}@example.com")
    assert [r["id"] for r in found["records"]] == [lead["id"]]
    tag = await mcp.call("create_tag", kind="lead", name=f"mcp-{suffix}")
    await mcp.call("add_tag", kind="lead", record_id=lead["id"], tag_id=tag["id"])

    pipeline = await mcp.call("crm_pipeline", include_deals=True)
    assert lead["id"] in [d["id"] for d in pipeline["deals"]]
    assert sum(stage["deals"] for stage in pipeline["stages"]) >= 1
    assert "health_flags" in pipeline


async def test_activities(mcp: _Mcp) -> None:
    suffix = _suffix()
    partner = await mcp.call(
        "create_record", model="res.partner", values={"name": f"MCP Activity {suffix}"}
    )
    todo = await mcp.call(
        "schedule_activity",
        model="res.partner",
        record_id=partner["id"],
        summary=f"Call back {suffix}",
        deadline="2020-01-01",
        note="Ask about the **invoice**",
    )
    listed = await mcp.call("list_activities", model="res.partner", record_id=partner["id"])
    assert [a["id"] for a in listed["records"]] == [todo["id"]]
    overdue = await mcp.call("list_activities", mine=True, overdue=True, limit=500)
    assert todo["id"] in [a["id"] for a in overdue["records"]]

    call = await mcp.call(
        "schedule_activity",
        model="res.partner",
        record_id=partner["id"],
        summary="Phone",
        deadline="2030-01-01",
        activity_type="Call",
    )
    await mcp.call("mark_activity_done", activity_id=call["id"])
    remaining = await mcp.call("list_activities", model="res.partner", record_id=partner["id"])
    assert [a["id"] for a in remaining["records"]] == [todo["id"]]


async def test_helpdesk(mcp: _Mcp) -> None:
    mcp.require("create_ticket")
    suffix = _suffix()
    ticket = await mcp.call(
        "create_ticket", name=f"MCP Ticket {suffix}", description="Printer *on fire*", priority="2"
    )
    found = await mcp.call("list_tickets", search=f"MCP Ticket {suffix}")
    assert [t["id"] for t in found["records"]] == [ticket["id"]]
    tag = await mcp.call("create_tag", kind="ticket", name=f"mcp-{suffix}")
    await mcp.call("add_tag", kind="ticket", record_id=ticket["id"], tag_id=tag["id"])
    read = await mcp.call("read_records", model="helpdesk.ticket", ids=[ticket["id"]])
    assert tag["id"] in read[0]["tag_ids"]


async def test_knowledge(mcp: _Mcp) -> None:
    mcp.require("create_article")
    suffix = _suffix()
    article = await mcp.call(
        "create_article", name=f"MCP Article {suffix}", body="# Hello\n\nSome **text**."
    )
    assert article["url"].startswith("http")
    found = await mcp.call("list_articles", name=f"MCP Article {suffix}")
    assert [a["id"] for a in found["records"]] == [article["id"]]
    read = await mcp.call(
        "read_records", model="knowledge.article", ids=[article["id"]], fields=["body"]
    )
    assert "**text**" in read[0]["body"]
    assert article["category"] == "workspace"

    private = await mcp.call("create_article", name=f"MCP Private {suffix}", private=True)
    assert private["category"] == "private"
    rows = await mcp.call(
        "read_records",
        model="knowledge.article",
        ids=[private["id"]],
        fields=["internal_permission", "article_member_ids"],
    )
    assert rows[0]["internal_permission"] == "none"  # other internal users: no access
    assert len(rows[0]["article_member_ids"]) == 1


async def test_documents(mcp: _Mcp, tmp_path: Path) -> None:
    mcp.require("upload_document")
    folders = await mcp.call("list_document_folders")
    if not folders:
        pytest.skip("No Documents folder in this database")
    folder_id = folders[0]["id"]
    source = tmp_path / f"mcp-{_suffix()}.txt"
    source.write_bytes(b"document body")
    uploaded = await mcp.call("upload_document", file_path=str(source), folder=folder_id)
    listed = await mcp.call("list_documents", folder=folder_id, search=source.name)
    assert [d["id"] for d in listed["records"]] == [uploaded["id"]]
    downloaded = await mcp.call("download_document", document_id=uploaded["id"])
    assert Path(downloaded["path"]).read_bytes() == b"document body"
