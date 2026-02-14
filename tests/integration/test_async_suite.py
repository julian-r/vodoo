"""Async integration tests for vodoo against a live Odoo instance.

Mirrors the sync test_suite.py to verify the ``vodoo.aio`` async API
works identically against Odoo 17, 18, and 19.

Community tests (project, project-task, crm, model, security) run on all versions.
Enterprise tests (helpdesk, knowledge, timer) require the enterprise flag.
"""

import contextlib
import tempfile
from pathlib import Path
from typing import Any

import pytest

from vodoo.aio.client import AsyncOdooClient
from vodoo.aio.transport import AsyncJSON2Transport, AsyncLegacyTransport
from vodoo.config import OdooConfig
from vodoo.exceptions import (
    RecordNotFoundError,
    TransportError,
    VodooError,
)

pytestmark = pytest.mark.anyio


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
async def async_client(odoo_config: OdooConfig) -> Any:
    """Authenticated AsyncOdooClient for the test instance."""
    async with AsyncOdooClient(odoo_config) as client:
        yield client


# ══════════════════════════════════════════════════════════════════════════════
# Transport / connection
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncConnection:
    """Verify the async client connects and picks the right transport."""

    async def test_authentication(self, async_client: AsyncOdooClient) -> None:
        uid = await async_client.get_uid()
        assert uid > 0

    async def test_transport_type_v17_v18(
        self, async_client: AsyncOdooClient, odoo_version: int
    ) -> None:
        if odoo_version >= 19:
            pytest.skip("Odoo 19 uses JSON-2")
        assert isinstance(async_client.transport, AsyncLegacyTransport)

    @pytest.mark.odoo19
    async def test_transport_type_v19(self, async_client: AsyncOdooClient) -> None:
        assert isinstance(async_client.transport, AsyncJSON2Transport)

    async def test_context_manager(self, odoo_config: OdooConfig) -> None:
        async with AsyncOdooClient(odoo_config) as client:
            uid = await client.get_uid()
            assert uid > 0


# ══════════════════════════════════════════════════════════════════════════════
# Generic model CRUD  (res.partner — available in every edition)
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncGenericCRUD:
    """Test async generic model operations."""

    async def test_create_read_update_delete(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import create_record, delete_record, search_records, update_record

        # Create
        rid = await create_record(
            async_client,
            "res.partner",
            {"name": "Vodoo Async Test Partner", "email": "vodoo-async@example.com"},
        )
        assert rid > 0

        # Read
        records = await search_records(async_client, "res.partner", domain=[["id", "=", rid]])
        assert len(records) == 1
        assert records[0]["name"] == "Vodoo Async Test Partner"

        # Update
        result = await update_record(async_client, "res.partner", rid, {"phone": "+1-555-0199"})
        assert result is True
        records = await search_records(
            async_client, "res.partner", domain=[["id", "=", rid]], fields=["phone"]
        )
        assert records[0]["phone"] == "+1-555-0199"

        # Delete
        assert await delete_record(async_client, "res.partner", rid) is True
        assert await search_records(async_client, "res.partner", domain=[["id", "=", rid]]) == []

    async def test_call_method(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import call_method

        result = await call_method(
            async_client, "res.partner", "name_search", args=["Administrator"]
        )
        assert isinstance(result, list)

    async def test_search_with_limit_and_order(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import search_records

        records = await search_records(
            async_client, "res.partner", limit=3, order="id asc", fields=["id", "name"]
        )
        assert len(records) <= 3
        if len(records) >= 2:
            assert records[0]["id"] <= records[1]["id"]

    async def test_fields_get(self, async_client: AsyncOdooClient) -> None:
        fields = await async_client.execute("res.partner", "fields_get")
        assert "name" in fields
        assert fields["name"]["type"] == "char"


# ══════════════════════════════════════════════════════════════════════════════
# Project (project.project)
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncProject:
    """Test async project.project operations."""

    @pytest.fixture(autouse=True)
    async def _create_project(self, async_client: AsyncOdooClient) -> Any:
        from vodoo.aio.generic import create_record, delete_record

        self.project_id = await create_record(
            async_client, "project.project", {"name": "Vodoo Async Test Project"}
        )
        yield
        with contextlib.suppress(Exception):
            await delete_record(async_client, "project.project", self.project_id)

    async def test_list_projects(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import list_projects

        projects = await list_projects(async_client, domain=[["id", "=", self.project_id]])
        assert len(projects) == 1
        assert projects[0]["name"] == "Vodoo Async Test Project"

    async def test_get_project(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import get_project

        project = await get_project(async_client, self.project_id)
        assert project["name"] == "Vodoo Async Test Project"

    async def test_set_project_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import get_project, set_project_fields

        await set_project_fields(
            async_client, self.project_id, {"description": "<p>Async Updated</p>"}
        )
        project = await get_project(async_client, self.project_id)
        assert "Async Updated" in str(project.get("description", ""))

    async def test_list_project_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import list_project_fields

        fields = await list_project_fields(async_client)
        assert "name" in fields
        assert "user_id" in fields

    async def test_project_url(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import get_project_url

        url = get_project_url(async_client, self.project_id)
        assert str(self.project_id) in url
        assert "project.project" in url or "/web#" in url

    async def test_project_comment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import add_comment, list_project_messages

        uid = await async_client.get_uid()
        success = await add_comment(
            async_client, self.project_id, "Async test comment", user_id=uid
        )
        assert success is True

        messages = await list_project_messages(async_client, self.project_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Async test comment" in b for b in bodies)

    async def test_project_note(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import add_note

        uid = await async_client.get_uid()
        success = await add_note(async_client, self.project_id, "Async internal note", user_id=uid)
        assert success is True

    async def test_project_attachment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import (
            create_project_attachment,
            list_project_attachments,
        )

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"async test attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = await create_project_attachment(async_client, self.project_id, tmp_path)
            assert att_id > 0

            attachments = await list_project_attachments(async_client, self.project_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_list_stages(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project_project import list_stages

        stages = await list_stages(async_client)
        assert isinstance(stages, list)


# ══════════════════════════════════════════════════════════════════════════════
# Project Tasks (project.task)
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncProjectTask:
    """Test async project.task operations."""

    @pytest.fixture(autouse=True)
    async def _create_project_and_task(self, async_client: AsyncOdooClient) -> Any:
        from vodoo.aio.generic import create_record, delete_record
        from vodoo.aio.project import create_task

        self.project_id = await create_record(
            async_client, "project.project", {"name": "Vodoo Async Task Test Project"}
        )
        self.task_id = await create_task(
            async_client, "Vodoo Async Test Task", project_id=self.project_id
        )
        yield
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                await delete_record(async_client, model, rid)

    async def test_list_tasks(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import list_tasks

        tasks = await list_tasks(async_client, domain=[["id", "=", self.task_id]])
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Vodoo Async Test Task"

    async def test_get_task(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import get_task

        task = await get_task(async_client, self.task_id)
        assert task["name"] == "Vodoo Async Test Task"

    async def test_set_task_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import get_task, set_task_fields

        await set_task_fields(async_client, self.task_id, {"priority": "1"})
        task = await get_task(async_client, self.task_id, fields=["priority"])
        assert task["priority"] == "1"

    async def test_list_task_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import list_task_fields

        fields = await list_task_fields(async_client)
        assert "name" in fields
        assert "project_id" in fields
        assert "stage_id" in fields

    async def test_task_url(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import get_task_url

        url = get_task_url(async_client, self.task_id)
        assert str(self.task_id) in url

    async def test_task_comment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import add_comment, list_task_messages

        uid = await async_client.get_uid()
        success = await add_comment(async_client, self.task_id, "Async task comment", user_id=uid)
        assert success is True

        messages = await list_task_messages(async_client, self.task_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Async task comment" in b for b in bodies)

    async def test_task_note(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import add_note

        uid = await async_client.get_uid()
        success = await add_note(async_client, self.task_id, "Async task note", user_id=uid)
        assert success is True

    async def test_task_attachment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import create_task_attachment, list_task_attachments

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"async task attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = await create_task_attachment(async_client, self.task_id, tmp_path)
            assert att_id > 0

            attachments = await list_task_attachments(async_client, self.task_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_download_attachment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.base import download_attachment
        from vodoo.aio.project import create_task_attachment

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"async download test content")
            tmp_path = Path(f.name)

        try:
            att_id = await create_task_attachment(async_client, self.task_id, tmp_path)

            with tempfile.TemporaryDirectory() as outdir:
                out = await download_attachment(
                    async_client, att_id, Path(outdir) / "downloaded.txt"
                )
                assert out.exists()
                assert out.read_bytes() == b"async download test content"
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_create_attachment_from_bytes(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.base import create_attachment, download_attachment, list_attachments

        content = b"bytes upload integration test content"
        att_id = await create_attachment(
            async_client,
            "project.task",
            self.task_id,
            data=content,
            name="bytes_test.txt",
        )
        try:
            assert isinstance(att_id, int)
            assert att_id > 0

            attachments = await list_attachments(async_client, "project.task", self.task_id)
            assert any(a["id"] == att_id for a in attachments)

            with tempfile.TemporaryDirectory() as outdir:
                out = await download_attachment(
                    async_client, att_id, Path(outdir) / "bytes_test.txt"
                )
                assert out.exists()
                assert out.read_bytes() == content
        finally:
            with contextlib.suppress(Exception):
                from vodoo.aio.generic import delete_record

                await delete_record(async_client, "ir.attachment", att_id)

    async def test_create_task_with_options(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import delete_record
        from vodoo.aio.project import create_task, get_task

        task_id = await create_task(
            async_client,
            "Async Task With Description",
            project_id=self.project_id,
            description="<p>Async description</p>",
        )
        try:
            task = await get_task(async_client, task_id)
            assert "Async description" in str(task.get("description", ""))
        finally:
            await delete_record(async_client, "project.task", task_id)

    async def test_tags_crud(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.project import (
            add_tag_to_task,
            create_tag,
            delete_tag,
            get_task,
            list_task_tags,
        )

        tag_id = await create_tag(async_client, "vodoo-async-test-tag")
        assert tag_id > 0

        try:
            tags = await list_task_tags(async_client)
            assert any(t["id"] == tag_id for t in tags)

            await add_tag_to_task(async_client, self.task_id, tag_id)

            task = await get_task(async_client, self.task_id, fields=["tag_ids"])
            assert tag_id in task.get("tag_ids", [])
        finally:
            await delete_tag(async_client, tag_id)

    async def test_subtask(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import delete_record
        from vodoo.aio.project import create_task, get_task

        sub_id = await create_task(
            async_client,
            "Vodoo Async Subtask",
            project_id=self.project_id,
            parent_id=self.task_id,
        )
        try:
            sub = await get_task(async_client, sub_id, fields=["parent_id"])
            parent = sub.get("parent_id")
            if isinstance(parent, list):
                assert parent[0] == self.task_id
            else:
                assert parent == self.task_id
        finally:
            await delete_record(async_client, "project.task", sub_id)


# ══════════════════════════════════════════════════════════════════════════════
# CRM (crm.lead)
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncCRM:
    """Test async CRM lead/opportunity operations."""

    @pytest.fixture(autouse=True)
    async def _create_lead(self, async_client: AsyncOdooClient) -> Any:
        from vodoo.aio.generic import create_record, delete_record

        self.lead_id = await create_record(
            async_client,
            "crm.lead",
            {
                "name": "Vodoo Async Test Lead",
                "email_from": "async-lead@example.com",
                "type": "opportunity",
            },
        )
        yield
        with contextlib.suppress(Exception):
            await delete_record(async_client, "crm.lead", self.lead_id)

    async def test_list_leads(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import list_leads

        leads = await list_leads(async_client, domain=[["id", "=", self.lead_id]])
        assert len(leads) == 1
        assert leads[0]["name"] == "Vodoo Async Test Lead"

    async def test_get_lead(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import get_lead

        lead = await get_lead(async_client, self.lead_id)
        assert lead["name"] == "Vodoo Async Test Lead"
        assert lead["email_from"] == "async-lead@example.com"

    async def test_set_lead_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import get_lead, set_lead_fields

        await set_lead_fields(async_client, self.lead_id, {"phone": "+1-555-0200"})
        lead = await get_lead(async_client, self.lead_id, fields=["phone"])
        assert lead["phone"] == "+1-555-0200"

    async def test_list_lead_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import list_lead_fields

        fields = await list_lead_fields(async_client)
        assert "name" in fields
        assert "stage_id" in fields
        assert "email_from" in fields

    async def test_lead_url(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import get_lead_url

        url = get_lead_url(async_client, self.lead_id)
        assert str(self.lead_id) in url

    async def test_lead_comment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import add_comment, list_lead_messages

        uid = await async_client.get_uid()
        success = await add_comment(async_client, self.lead_id, "Async lead comment", user_id=uid)
        assert success is True

        messages = await list_lead_messages(async_client, self.lead_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Async lead comment" in b for b in bodies)

    async def test_lead_note(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import add_note

        uid = await async_client.get_uid()
        success = await add_note(async_client, self.lead_id, "Async lead note", user_id=uid)
        assert success is True

    async def test_lead_attachment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import create_lead_attachment, list_lead_attachments

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"async lead attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = await create_lead_attachment(async_client, self.lead_id, tmp_path)
            assert att_id > 0

            attachments = await list_lead_attachments(async_client, self.lead_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_lead_tags(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import add_tag_to_lead, get_lead, list_tags
        from vodoo.aio.generic import create_record, delete_record

        tag_id = await create_record(async_client, "crm.tag", {"name": "vodoo-async-crm-tag"})
        try:
            tags = await list_tags(async_client)
            assert any(t["id"] == tag_id for t in tags)

            await add_tag_to_lead(async_client, self.lead_id, tag_id)

            lead = await get_lead(async_client, self.lead_id, fields=["tag_ids"])
            assert tag_id in lead.get("tag_ids", [])
        finally:
            await delete_record(async_client, "crm.tag", tag_id)

    async def test_download_all_attachments(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.crm import create_lead_attachment, download_lead_attachments

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-async-fake-content")
            tmp_path = Path(f.name)

        try:
            await create_lead_attachment(async_client, self.lead_id, tmp_path)

            with tempfile.TemporaryDirectory() as outdir:
                downloaded = await download_lead_attachments(
                    async_client, self.lead_id, Path(outdir)
                )
                assert len(downloaded) >= 1
        finally:
            tmp_path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Security
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncSecurity:
    """Test async security group utilities."""

    async def test_create_security_groups(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.security import create_security_groups

        group_ids, _warnings = await create_security_groups(async_client)
        assert len(group_ids) > 0
        # Should be idempotent
        group_ids2, _ = await create_security_groups(async_client)
        assert group_ids == group_ids2

    async def test_create_user(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import delete_record
        from vodoo.aio.security import create_user, get_user_info

        user_id, _password = await create_user(
            async_client,
            name="Vodoo Async Test Bot",
            login="vodoo-async-bot@example.com",
            password="TestPassword123",
        )
        try:
            assert user_id > 0
            info = await get_user_info(async_client, user_id)
            assert info["login"] == "vodoo-async-bot@example.com"
            assert info["name"] == "Vodoo Async Test Bot"
        finally:
            with contextlib.suppress(Exception):
                await delete_record(async_client, "res.users", user_id)

    async def test_resolve_user_id(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.security import resolve_user_id

        uid = await resolve_user_id(async_client, user_id=None, login="admin")
        assert uid > 0

    async def test_set_user_password(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import delete_record
        from vodoo.aio.security import create_user, set_user_password

        user_id, _ = await create_user(
            async_client,
            name="Vodoo Async PW Test",
            login="vodoo-async-pw-test@example.com",
        )
        try:
            new_pw = await set_user_password(async_client, user_id, "NewPassword456")
            assert new_pw == "NewPassword456"

            gen_pw = await set_user_password(async_client, user_id)
            assert len(gen_pw) > 8
        finally:
            with contextlib.suppress(Exception):
                await delete_record(async_client, "res.users", user_id)

    async def test_assign_bot_to_groups(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import delete_record
        from vodoo.aio.security import (
            assign_user_to_groups,
            create_security_groups,
            create_user,
        )

        group_ids, _ = await create_security_groups(async_client)
        user_id, _ = await create_user(
            async_client,
            name="Vodoo Async Group Test",
            login="vodoo-async-group-test@example.com",
        )
        try:
            await assign_user_to_groups(
                async_client, user_id, list(group_ids.values()), remove_default_groups=True
            )
            for fname in ("group_ids", "groups_id"):
                try:
                    user = await async_client.read("res.users", [user_id], [fname])
                    user_groups = user[0][fname]
                    break
                except Exception:
                    continue
            else:
                pytest.fail("Could not read user groups field")
            for gid in group_ids.values():
                assert gid in user_groups
        finally:
            with contextlib.suppress(Exception):
                await delete_record(async_client, "res.users", user_id)


# ══════════════════════════════════════════════════════════════════════════════
# Helpdesk (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestAsyncHelpdesk:
    """Test async helpdesk.ticket operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    async def _create_ticket(self, async_client: AsyncOdooClient) -> Any:
        from vodoo.aio.generic import create_record, delete_record

        teams = await async_client.search_read("helpdesk.team", limit=1, fields=["id"])
        if teams:
            self.team_id = teams[0]["id"]
        else:
            self.team_id = await create_record(
                async_client, "helpdesk.team", {"name": "Vodoo Async Test Team"}
            )

        self.ticket_id = await create_record(
            async_client,
            "helpdesk.ticket",
            {"name": "Vodoo Async Test Ticket", "team_id": self.team_id},
        )
        yield
        with contextlib.suppress(Exception):
            await delete_record(async_client, "helpdesk.ticket", self.ticket_id)

    async def test_list_tickets(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import list_tickets

        tickets = await list_tickets(async_client, domain=[["id", "=", self.ticket_id]])
        assert len(tickets) == 1
        assert tickets[0]["name"] == "Vodoo Async Test Ticket"

    async def test_get_ticket(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import get_ticket

        ticket = await get_ticket(async_client, self.ticket_id)
        assert ticket["name"] == "Vodoo Async Test Ticket"

    async def test_set_ticket_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import get_ticket, set_ticket_fields

        await set_ticket_fields(async_client, self.ticket_id, {"priority": "2"})
        ticket = await get_ticket(async_client, self.ticket_id, fields=["priority"])
        assert ticket["priority"] == "2"

    async def test_list_ticket_fields(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import list_ticket_fields

        fields = await list_ticket_fields(async_client)
        assert "name" in fields
        assert "team_id" in fields

    async def test_ticket_url(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import get_ticket_url

        url = get_ticket_url(async_client, self.ticket_id)
        assert str(self.ticket_id) in url

    async def test_ticket_comment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import add_comment, list_messages

        uid = await async_client.get_uid()
        success = await add_comment(
            async_client, self.ticket_id, "Async ticket comment", user_id=uid
        )
        assert success is True

        messages = await list_messages(async_client, self.ticket_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Async ticket comment" in b for b in bodies)

    async def test_ticket_note(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import add_note

        uid = await async_client.get_uid()
        success = await add_note(async_client, self.ticket_id, "Async ticket note", user_id=uid)
        assert success is True

    async def test_ticket_attachment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import create_attachment, list_attachments

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"async ticket attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = await create_attachment(async_client, self.ticket_id, tmp_path)
            assert att_id > 0

            attachments = await list_attachments(async_client, self.ticket_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    async def test_ticket_attachment_from_bytes(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.helpdesk import create_attachment, list_attachments

        att_id = await create_attachment(
            async_client, self.ticket_id, data=b"bytes upload test", name="test.txt"
        )
        assert isinstance(att_id, int)
        assert att_id > 0

        attachments = await list_attachments(async_client, self.ticket_id)
        assert any(a["id"] == att_id for a in attachments)

    async def test_ticket_tags(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import create_record, delete_record
        from vodoo.aio.helpdesk import add_tag_to_ticket, get_ticket, list_tags

        tag_id = await create_record(
            async_client, "helpdesk.tag", {"name": "vodoo-async-helpdesk-tag"}
        )
        try:
            tags = await list_tags(async_client)
            assert any(t["id"] == tag_id for t in tags)

            await add_tag_to_ticket(async_client, self.ticket_id, tag_id)
            ticket = await get_ticket(async_client, self.ticket_id, fields=["tag_ids"])
            assert tag_id in ticket.get("tag_ids", [])
        finally:
            await delete_record(async_client, "helpdesk.tag", tag_id)

    async def test_create_ticket(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import delete_record
        from vodoo.aio.helpdesk import create_ticket, get_ticket

        ticket_id = await create_ticket(
            async_client,
            "Vodoo Async Create Test Ticket",
            team_id=self.team_id,
            description="<p>Async test description</p>",
        )
        try:
            assert ticket_id > 0
            ticket = await get_ticket(async_client, ticket_id)
            assert ticket["name"] == "Vodoo Async Create Test Ticket"
            assert "Async test description" in str(ticket.get("description", ""))
        finally:
            with contextlib.suppress(Exception):
                await delete_record(async_client, "helpdesk.ticket", ticket_id)

    async def test_create_ticket_with_tags(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.generic import create_record, delete_record
        from vodoo.aio.helpdesk import create_ticket, get_ticket

        tag_id = await create_record(
            async_client, "helpdesk.tag", {"name": "vodoo-async-create-test-tag"}
        )
        ticket_id = None
        try:
            ticket_id = await create_ticket(
                async_client,
                "Vodoo Async Tag Test Ticket",
                team_id=self.team_id,
                tag_ids=[tag_id],
            )
            assert ticket_id > 0
            ticket = await get_ticket(async_client, ticket_id, fields=["tag_ids"])
            assert tag_id in ticket.get("tag_ids", [])
        finally:
            if ticket_id is not None:
                with contextlib.suppress(Exception):
                    await delete_record(async_client, "helpdesk.ticket", ticket_id)
            with contextlib.suppress(Exception):
                await delete_record(async_client, "helpdesk.tag", tag_id)


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestAsyncKnowledge:
    """Test async knowledge.article operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    async def _create_article(self, async_client: AsyncOdooClient) -> Any:
        from vodoo.aio.generic import create_record, delete_record

        self.article_id = await create_record(
            async_client,
            "knowledge.article",
            {"name": "Vodoo Async Test Article", "body": "<p>Async test body</p>"},
        )
        yield
        with contextlib.suppress(Exception):
            await delete_record(async_client, "knowledge.article", self.article_id)

    async def test_list_articles(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.knowledge import list_articles

        articles = await list_articles(async_client, domain=[["id", "=", self.article_id]])
        assert len(articles) == 1
        assert articles[0]["name"] == "Vodoo Async Test Article"

    async def test_get_article(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.knowledge import get_article

        article = await get_article(async_client, self.article_id)
        assert article["name"] == "Vodoo Async Test Article"

    async def test_article_url(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.knowledge import get_article_url

        url = await get_article_url(async_client, self.article_id)
        assert str(self.article_id) in url

    async def test_article_comment(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.knowledge import add_comment, list_article_messages

        uid = await async_client.get_uid()
        success = await add_comment(
            async_client, self.article_id, "Async article comment", user_id=uid
        )
        assert success is True

        messages = await list_article_messages(async_client, self.article_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Async article comment" in b for b in bodies)

    async def test_article_note(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.knowledge import add_note

        uid = await async_client.get_uid()
        success = await add_note(async_client, self.article_id, "Async article note", user_id=uid)
        assert success is True

    async def test_article_attachments(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.knowledge import list_article_attachments

        attachments = await list_article_attachments(async_client, self.article_id)
        assert isinstance(attachments, list)


# ══════════════════════════════════════════════════════════════════════════════
# Timer / Timesheet (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestAsyncTimer:
    """Test async timer/timesheet operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    async def _create_project_and_task(self, async_client: AsyncOdooClient) -> Any:
        from vodoo.aio.generic import create_record, delete_record
        from vodoo.aio.project import create_task

        self.project_id = await create_record(
            async_client,
            "project.project",
            {"name": "Vodoo Async Timer Test Project", "allow_timesheets": True},
        )
        self.task_id = await create_task(
            async_client, "Vodoo Async Timer Test Task", project_id=self.project_id
        )
        yield
        with contextlib.suppress(Exception):
            from vodoo.aio.timer import stop_active_timers

            await stop_active_timers(async_client)
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                await delete_record(async_client, model, rid)

    async def test_start_stop_timer_on_task(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.timer import (
            fetch_active_timesheets,
            start_timer_on_task,
            stop_active_timers,
        )

        await start_timer_on_task(async_client, self.task_id)

        active = await fetch_active_timesheets(async_client)
        assert len(active) >= 1

        stopped = await stop_active_timers(async_client)
        assert len(stopped) >= 1

    async def test_today_timesheets(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.timer import (
            fetch_today_timesheets,
            start_timer_on_task,
            stop_active_timers,
        )

        await start_timer_on_task(async_client, self.task_id)
        try:
            timesheets = await fetch_today_timesheets(async_client)
            assert len(timesheets) >= 1
        finally:
            await stop_active_timers(async_client)


# ══════════════════════════════════════════════════════════════════════════════
# Exception hierarchy (live server)
# ══════════════════════════════════════════════════════════════════════════════


class TestAsyncExceptions:
    """Verify Vodoo exceptions are raised correctly via async client."""

    async def test_record_not_found(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.base import get_record

        with pytest.raises(RecordNotFoundError) as exc_info:
            await get_record(async_client, "res.partner", 999999999)

        assert exc_info.value.model == "res.partner"
        assert exc_info.value.record_id == 999999999

    async def test_record_not_found_is_vodoo_error(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.base import get_record

        with pytest.raises(VodooError):
            await get_record(async_client, "res.partner", 999999999)

    async def test_access_error_on_forbidden_model(self, async_client: AsyncOdooClient) -> None:
        from vodoo.aio.security import create_user

        user_id, password = await create_user(
            async_client,
            name="Vodoo Async Exception Test User",
            login="vodoo-async-exc-test@example.com",
        )
        try:
            unprivileged_config = OdooConfig(
                url=async_client.config.url,
                database=async_client.config.database,
                username="vodoo-async-exc-test@example.com",
                password=password,
            )
            async with AsyncOdooClient(unprivileged_config, auto_detect=False) as unpriv:
                with pytest.raises(TransportError) as exc_info:
                    await unpriv.write("res.partner", [1], {"name": "Should Fail"})

                assert isinstance(exc_info.value, VodooError)
        finally:
            with contextlib.suppress(Exception):
                from vodoo.aio.generic import delete_record

                await delete_record(async_client, "res.users", user_id)

    async def test_validation_error_on_bad_data(self, async_client: AsyncOdooClient) -> None:
        with pytest.raises(TransportError):
            await async_client.create(
                "res.users",
                {
                    "name": "Async Duplicate Admin",
                    "login": "admin",
                    "password": "test",
                },
            )
