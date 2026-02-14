"""Integration tests for vodoo against a live Odoo instance.

Community tests (project, project-task, crm, model, security) run on all versions.
Enterprise tests (helpdesk, knowledge, timer) require the enterprise flag.
"""

import contextlib
import tempfile
from pathlib import Path
from typing import Any

import pytest

from vodoo.client import OdooClient
from vodoo.exceptions import (
    RecordNotFoundError,
    TransportError,
    VodooError,
)
from vodoo.transport import JSON2Transport, LegacyTransport

# ══════════════════════════════════════════════════════════════════════════════
# Transport / connection
# ══════════════════════════════════════════════════════════════════════════════


class TestConnection:
    """Verify the client connects and picks the right transport."""

    def test_authentication(self, client: OdooClient) -> None:
        assert client.uid > 0

    def test_transport_type_v17_v18(self, client: OdooClient, odoo_version: int) -> None:
        if odoo_version >= 19:
            pytest.skip("Odoo 19 uses JSON-2")
        assert isinstance(client.transport, LegacyTransport)

    @pytest.mark.odoo19
    def test_transport_type_v19(self, client: OdooClient) -> None:
        assert isinstance(client.transport, JSON2Transport)


# ══════════════════════════════════════════════════════════════════════════════
# Generic model CRUD  (res.partner — available in every edition)
# ══════════════════════════════════════════════════════════════════════════════


class TestGenericCRUD:
    """Test generic model operations via the ``model`` subcommand layer."""

    def test_create_read_update_delete(self, client: OdooClient) -> None:
        from vodoo.generic import create_record, delete_record, search_records, update_record

        # Create
        rid = create_record(
            client,
            "res.partner",
            {"name": "Vodoo Test Partner", "email": "vodoo-test@example.com"},
        )
        assert rid > 0

        # Read
        records = search_records(client, "res.partner", domain=[["id", "=", rid]])
        assert len(records) == 1
        assert records[0]["name"] == "Vodoo Test Partner"

        # Update
        assert update_record(client, "res.partner", rid, {"phone": "+1-555-0199"}) is True
        records = search_records(client, "res.partner", domain=[["id", "=", rid]], fields=["phone"])
        assert records[0]["phone"] == "+1-555-0199"

        # Delete
        assert delete_record(client, "res.partner", rid) is True
        assert search_records(client, "res.partner", domain=[["id", "=", rid]]) == []

    def test_call_method(self, client: OdooClient) -> None:
        from vodoo.generic import call_method

        result = call_method(client, "res.partner", "name_search", args=["Administrator"])
        assert isinstance(result, list)

    def test_search_with_limit_and_order(self, client: OdooClient) -> None:
        from vodoo.generic import search_records

        records = search_records(
            client, "res.partner", limit=3, order="id asc", fields=["id", "name"]
        )
        assert len(records) <= 3
        if len(records) >= 2:
            assert records[0]["id"] <= records[1]["id"]

    def test_fields_get(self, client: OdooClient) -> None:
        fields = client.execute("res.partner", "fields_get")
        assert "name" in fields
        assert fields["name"]["type"] == "char"


# ══════════════════════════════════════════════════════════════════════════════
# Project (project.project)
# ══════════════════════════════════════════════════════════════════════════════


class TestProject:
    """Test project.project operations."""

    @pytest.fixture(autouse=True)
    def _create_project(self, client: OdooClient) -> Any:
        """Create a project for testing and clean up afterwards."""
        from vodoo.generic import create_record, delete_record

        self.project_id = create_record(client, "project.project", {"name": "Vodoo Test Project"})
        yield
        with contextlib.suppress(Exception):
            delete_record(client, "project.project", self.project_id)

    def test_list_projects(self, client: OdooClient) -> None:
        from vodoo.project_project import list_projects

        projects = list_projects(client, domain=[["id", "=", self.project_id]])
        assert len(projects) == 1
        assert projects[0]["name"] == "Vodoo Test Project"

    def test_get_project(self, client: OdooClient) -> None:
        from vodoo.project_project import get_project

        project = get_project(client, self.project_id)
        assert project["name"] == "Vodoo Test Project"

    def test_set_project_fields(self, client: OdooClient) -> None:
        from vodoo.project_project import get_project, set_project_fields

        set_project_fields(client, self.project_id, {"description": "<p>Updated</p>"})
        project = get_project(client, self.project_id)
        assert "Updated" in str(project.get("description", ""))

    def test_list_project_fields(self, client: OdooClient) -> None:
        from vodoo.project_project import list_project_fields

        fields = list_project_fields(client)
        assert "name" in fields
        assert "user_id" in fields

    def test_project_url(self, client: OdooClient) -> None:
        from vodoo.project_project import get_project_url

        url = get_project_url(client, self.project_id)
        assert str(self.project_id) in url
        assert "project.project" in url or "/web#" in url

    def test_project_comment(self, client: OdooClient) -> None:
        from vodoo.project_project import add_comment, list_project_messages

        success = add_comment(
            client, self.project_id, "Test comment from vodoo", user_id=client.uid
        )
        assert success is True

        messages = list_project_messages(client, self.project_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Test comment from vodoo" in b for b in bodies)

    def test_project_note(self, client: OdooClient) -> None:
        from vodoo.project_project import add_note

        success = add_note(client, self.project_id, "Internal note from vodoo", user_id=client.uid)
        assert success is True

    def test_project_attachment(self, client: OdooClient) -> None:
        from vodoo.project_project import (
            create_project_attachment,
            list_project_attachments,
        )

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = create_project_attachment(client, self.project_id, tmp_path)
            assert att_id > 0

            attachments = list_project_attachments(client, self.project_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_list_stages(self, client: OdooClient) -> None:
        from vodoo.project_project import list_stages

        stages = list_stages(client)
        assert isinstance(stages, list)


# ══════════════════════════════════════════════════════════════════════════════
# Project Tasks (project.task)
# ══════════════════════════════════════════════════════════════════════════════


class TestProjectTask:
    """Test project.task operations."""

    @pytest.fixture(autouse=True)
    def _create_project_and_task(self, client: OdooClient) -> Any:
        from vodoo.generic import create_record, delete_record
        from vodoo.project import create_task

        self.project_id = create_record(
            client, "project.project", {"name": "Vodoo Task Test Project"}
        )
        self.task_id = create_task(client, "Vodoo Test Task", project_id=self.project_id)
        yield
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                delete_record(client, model, rid)

    def test_list_tasks(self, client: OdooClient) -> None:
        from vodoo.project import list_tasks

        tasks = list_tasks(client, domain=[["id", "=", self.task_id]])
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Vodoo Test Task"

    def test_get_task(self, client: OdooClient) -> None:
        from vodoo.project import get_task

        task = get_task(client, self.task_id)
        assert task["name"] == "Vodoo Test Task"

    def test_set_task_fields(self, client: OdooClient) -> None:
        from vodoo.project import get_task, set_task_fields

        set_task_fields(client, self.task_id, {"priority": "1"})
        task = get_task(client, self.task_id, fields=["priority"])
        assert task["priority"] == "1"

    def test_list_task_fields(self, client: OdooClient) -> None:
        from vodoo.project import list_task_fields

        fields = list_task_fields(client)
        assert "name" in fields
        assert "project_id" in fields
        assert "stage_id" in fields

    def test_task_url(self, client: OdooClient) -> None:
        from vodoo.project import get_task_url

        url = get_task_url(client, self.task_id)
        assert str(self.task_id) in url

    def test_task_comment(self, client: OdooClient) -> None:
        from vodoo.project import add_comment, list_task_messages

        success = add_comment(client, self.task_id, "Task comment from vodoo", user_id=client.uid)
        assert success is True

        messages = list_task_messages(client, self.task_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Task comment from vodoo" in b for b in bodies)

    def test_task_note(self, client: OdooClient) -> None:
        from vodoo.project import add_note

        success = add_note(client, self.task_id, "Task internal note", user_id=client.uid)
        assert success is True

    def test_task_attachment(self, client: OdooClient) -> None:
        from vodoo.project import create_task_attachment, list_task_attachments

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"task attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = create_task_attachment(client, self.task_id, tmp_path)
            assert att_id > 0

            attachments = list_task_attachments(client, self.task_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_download_attachment(self, client: OdooClient) -> None:
        from vodoo.base import download_attachment
        from vodoo.project import create_task_attachment

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"download test content")
            tmp_path = Path(f.name)

        try:
            att_id = create_task_attachment(client, self.task_id, tmp_path)

            with tempfile.TemporaryDirectory() as outdir:
                out = download_attachment(client, att_id, Path(outdir) / "downloaded.txt")
                assert out.exists()
                assert out.read_bytes() == b"download test content"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_create_task_with_options(self, client: OdooClient) -> None:
        from vodoo.generic import delete_record
        from vodoo.project import create_task, get_task

        task_id = create_task(
            client,
            "Task With Description",
            project_id=self.project_id,
            description="<p>Some description</p>",
        )
        try:
            task = get_task(client, task_id)
            assert "Some description" in str(task.get("description", ""))
        finally:
            delete_record(client, "project.task", task_id)

    def test_tags_crud(self, client: OdooClient) -> None:
        from vodoo.project import (
            add_tag_to_task,
            create_tag,
            delete_tag,
            get_task,
            list_task_tags,
        )

        # Create tag
        tag_id = create_tag(client, "vodoo-test-tag")
        assert tag_id > 0

        try:
            # List tags
            tags = list_task_tags(client)
            assert any(t["id"] == tag_id for t in tags)

            # Add tag to task
            add_tag_to_task(client, self.task_id, tag_id)

            # Verify
            task = get_task(client, self.task_id, fields=["tag_ids"])
            tag_ids = task.get("tag_ids", [])
            assert tag_id in tag_ids
        finally:
            delete_tag(client, tag_id)

    def test_subtask(self, client: OdooClient) -> None:
        from vodoo.generic import delete_record
        from vodoo.project import create_task, get_task

        sub_id = create_task(
            client, "Vodoo Subtask", project_id=self.project_id, parent_id=self.task_id
        )
        try:
            sub = get_task(client, sub_id, fields=["parent_id"])
            parent = sub.get("parent_id")
            if isinstance(parent, list):
                assert parent[0] == self.task_id
            else:
                assert parent == self.task_id
        finally:
            delete_record(client, "project.task", sub_id)


# ══════════════════════════════════════════════════════════════════════════════
# CRM (crm.lead)
# ══════════════════════════════════════════════════════════════════════════════


class TestCRM:
    """Test CRM lead/opportunity operations."""

    @pytest.fixture(autouse=True)
    def _create_lead(self, client: OdooClient) -> Any:
        from vodoo.generic import create_record, delete_record

        self.lead_id = create_record(
            client,
            "crm.lead",
            {
                "name": "Vodoo Test Lead",
                "email_from": "lead-test@example.com",
                "type": "opportunity",
            },
        )
        yield
        with contextlib.suppress(Exception):
            delete_record(client, "crm.lead", self.lead_id)

    def test_list_leads(self, client: OdooClient) -> None:
        from vodoo.crm import list_leads

        leads = list_leads(client, domain=[["id", "=", self.lead_id]])
        assert len(leads) == 1
        assert leads[0]["name"] == "Vodoo Test Lead"

    def test_get_lead(self, client: OdooClient) -> None:
        from vodoo.crm import get_lead

        lead = get_lead(client, self.lead_id)
        assert lead["name"] == "Vodoo Test Lead"
        assert lead["email_from"] == "lead-test@example.com"

    def test_set_lead_fields(self, client: OdooClient) -> None:
        from vodoo.crm import get_lead, set_lead_fields

        set_lead_fields(client, self.lead_id, {"phone": "+1-555-0100"})
        lead = get_lead(client, self.lead_id, fields=["phone"])
        assert lead["phone"] == "+1-555-0100"

    def test_list_lead_fields(self, client: OdooClient) -> None:
        from vodoo.crm import list_lead_fields

        fields = list_lead_fields(client)
        assert "name" in fields
        assert "stage_id" in fields
        assert "email_from" in fields

    def test_lead_url(self, client: OdooClient) -> None:
        from vodoo.crm import get_lead_url

        url = get_lead_url(client, self.lead_id)
        assert str(self.lead_id) in url

    def test_lead_comment(self, client: OdooClient) -> None:
        from vodoo.crm import add_comment, list_lead_messages

        success = add_comment(client, self.lead_id, "Lead comment from vodoo", user_id=client.uid)
        assert success is True

        messages = list_lead_messages(client, self.lead_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Lead comment from vodoo" in b for b in bodies)

    def test_lead_note(self, client: OdooClient) -> None:
        from vodoo.crm import add_note

        success = add_note(client, self.lead_id, "Lead internal note", user_id=client.uid)
        assert success is True

    def test_lead_attachment(self, client: OdooClient) -> None:
        from vodoo.crm import create_lead_attachment, list_lead_attachments

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"lead attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = create_lead_attachment(client, self.lead_id, tmp_path)
            assert att_id > 0

            attachments = list_lead_attachments(client, self.lead_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_lead_tags(self, client: OdooClient) -> None:
        from vodoo.crm import add_tag_to_lead, get_lead, list_tags
        from vodoo.generic import create_record, delete_record

        tag_id = create_record(client, "crm.tag", {"name": "vodoo-crm-test-tag"})
        try:
            tags = list_tags(client)
            assert any(t["id"] == tag_id for t in tags)

            add_tag_to_lead(client, self.lead_id, tag_id)

            lead = get_lead(client, self.lead_id, fields=["tag_ids"])
            assert tag_id in lead.get("tag_ids", [])
        finally:
            delete_record(client, "crm.tag", tag_id)

    def test_download_all_attachments(self, client: OdooClient) -> None:
        from vodoo.crm import create_lead_attachment, download_lead_attachments

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-fake-content")
            tmp_path = Path(f.name)

        try:
            create_lead_attachment(client, self.lead_id, tmp_path)

            with tempfile.TemporaryDirectory() as outdir:
                downloaded = download_lead_attachments(client, self.lead_id, Path(outdir))
                assert len(downloaded) >= 1
        finally:
            tmp_path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Security
# ══════════════════════════════════════════════════════════════════════════════


class TestSecurity:
    """Test security group utilities."""

    def test_create_security_groups(self, client: OdooClient) -> None:
        from vodoo.security import create_security_groups

        group_ids, _warnings = create_security_groups(client)
        assert len(group_ids) > 0
        # Should be idempotent
        group_ids2, _ = create_security_groups(client)
        assert group_ids == group_ids2

    def test_create_user(self, client: OdooClient) -> None:
        from vodoo.generic import delete_record
        from vodoo.security import create_user, get_user_info

        user_id, _password = create_user(
            client,
            name="Vodoo Test Bot",
            login="vodoo-bot@example.com",
            password="TestPassword123",
        )
        try:
            assert user_id > 0
            info = get_user_info(client, user_id)
            assert info["login"] == "vodoo-bot@example.com"
            assert info["name"] == "Vodoo Test Bot"
        finally:
            with contextlib.suppress(Exception):
                delete_record(client, "res.users", user_id)

    def test_resolve_user_id(self, client: OdooClient) -> None:
        from vodoo.security import resolve_user_id

        uid = resolve_user_id(client, user_id=None, login="admin")
        assert uid > 0

    def test_set_user_password(self, client: OdooClient) -> None:
        from vodoo.generic import delete_record
        from vodoo.security import create_user, set_user_password

        user_id, _ = create_user(
            client,
            name="Vodoo PW Test",
            login="vodoo-pw-test@example.com",
        )
        try:
            new_pw = set_user_password(client, user_id, "NewPassword456")
            assert new_pw == "NewPassword456"

            # Also test generated password
            gen_pw = set_user_password(client, user_id)
            assert len(gen_pw) > 8
        finally:
            with contextlib.suppress(Exception):
                delete_record(client, "res.users", user_id)

    def test_assign_bot_to_groups(self, client: OdooClient) -> None:
        from vodoo.generic import delete_record
        from vodoo.security import (
            assign_user_to_groups,
            create_security_groups,
            create_user,
        )

        group_ids, _ = create_security_groups(client)
        user_id, _ = create_user(
            client,
            name="Vodoo Group Test",
            login="vodoo-group-test@example.com",
        )
        try:
            assign_user_to_groups(
                client, user_id, list(group_ids.values()), remove_default_groups=True
            )
            # Verify assignment — field name differs by version
            for fname in ("group_ids", "groups_id"):
                try:
                    user = client.read("res.users", [user_id], [fname])
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
                delete_record(client, "res.users", user_id)


# ══════════════════════════════════════════════════════════════════════════════
# Helpdesk (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestHelpdesk:
    """Test helpdesk.ticket operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    def _create_ticket(self, client: OdooClient) -> Any:
        from vodoo.generic import create_record, delete_record

        # Helpdesk needs a team; find or create one
        teams = client.search_read("helpdesk.team", limit=1, fields=["id"])
        if teams:
            self.team_id = teams[0]["id"]
        else:
            self.team_id = create_record(client, "helpdesk.team", {"name": "Vodoo Test Team"})

        self.ticket_id = create_record(
            client,
            "helpdesk.ticket",
            {"name": "Vodoo Test Ticket", "team_id": self.team_id},
        )
        yield
        with contextlib.suppress(Exception):
            delete_record(client, "helpdesk.ticket", self.ticket_id)

    def test_list_tickets(self, client: OdooClient) -> None:
        from vodoo.helpdesk import list_tickets

        tickets = list_tickets(client, domain=[["id", "=", self.ticket_id]])
        assert len(tickets) == 1
        assert tickets[0]["name"] == "Vodoo Test Ticket"

    def test_get_ticket(self, client: OdooClient) -> None:
        from vodoo.helpdesk import get_ticket

        ticket = get_ticket(client, self.ticket_id)
        assert ticket["name"] == "Vodoo Test Ticket"

    def test_set_ticket_fields(self, client: OdooClient) -> None:
        from vodoo.helpdesk import get_ticket, set_ticket_fields

        set_ticket_fields(client, self.ticket_id, {"priority": "2"})
        ticket = get_ticket(client, self.ticket_id, fields=["priority"])
        assert ticket["priority"] == "2"

    def test_list_ticket_fields(self, client: OdooClient) -> None:
        from vodoo.helpdesk import list_ticket_fields

        fields = list_ticket_fields(client)
        assert "name" in fields
        assert "team_id" in fields

    def test_ticket_url(self, client: OdooClient) -> None:
        from vodoo.helpdesk import get_ticket_url

        url = get_ticket_url(client, self.ticket_id)
        assert str(self.ticket_id) in url

    def test_ticket_comment(self, client: OdooClient) -> None:
        from vodoo.helpdesk import add_comment, list_messages

        success = add_comment(
            client, self.ticket_id, "Ticket comment from vodoo", user_id=client.uid
        )
        assert success is True

        messages = list_messages(client, self.ticket_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Ticket comment from vodoo" in b for b in bodies)

    def test_ticket_note(self, client: OdooClient) -> None:
        from vodoo.helpdesk import add_note

        success = add_note(client, self.ticket_id, "Ticket internal note", user_id=client.uid)
        assert success is True

    def test_ticket_attachment(self, client: OdooClient) -> None:
        from vodoo.helpdesk import create_attachment, list_attachments

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"ticket attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = create_attachment(client, self.ticket_id, tmp_path)
            assert att_id > 0

            attachments = list_attachments(client, self.ticket_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_ticket_tags(self, client: OdooClient) -> None:
        from vodoo.generic import create_record, delete_record
        from vodoo.helpdesk import add_tag_to_ticket, get_ticket, list_tags

        tag_id = create_record(client, "helpdesk.tag", {"name": "vodoo-helpdesk-test-tag"})
        try:
            tags = list_tags(client)
            assert any(t["id"] == tag_id for t in tags)

            add_tag_to_ticket(client, self.ticket_id, tag_id)
            ticket = get_ticket(client, self.ticket_id, fields=["tag_ids"])
            assert tag_id in ticket.get("tag_ids", [])
        finally:
            delete_record(client, "helpdesk.tag", tag_id)

    def test_create_ticket(self, client: OdooClient) -> None:
        from vodoo.generic import delete_record
        from vodoo.helpdesk import create_ticket, get_ticket

        ticket_id = create_ticket(
            client,
            "Vodoo Create Test Ticket",
            team_id=self.team_id,
            description="<p>Test description</p>",
        )
        try:
            assert ticket_id > 0
            ticket = get_ticket(client, ticket_id)
            assert ticket["name"] == "Vodoo Create Test Ticket"
            assert "Test description" in str(ticket.get("description", ""))
        finally:
            with contextlib.suppress(Exception):
                delete_record(client, "helpdesk.ticket", ticket_id)

    def test_create_ticket_with_tags(self, client: OdooClient) -> None:
        from vodoo.generic import create_record, delete_record
        from vodoo.helpdesk import create_ticket, get_ticket

        tag_id = create_record(client, "helpdesk.tag", {"name": "vodoo-create-test-tag"})
        ticket_id = None
        try:
            ticket_id = create_ticket(
                client,
                "Vodoo Tag Test Ticket",
                team_id=self.team_id,
                tag_ids=[tag_id],
            )
            assert ticket_id > 0
            ticket = get_ticket(client, ticket_id, fields=["tag_ids"])
            assert tag_id in ticket.get("tag_ids", [])
        finally:
            if ticket_id is not None:
                with contextlib.suppress(Exception):
                    delete_record(client, "helpdesk.ticket", ticket_id)
            with contextlib.suppress(Exception):
                delete_record(client, "helpdesk.tag", tag_id)


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestKnowledge:
    """Test knowledge.article operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    def _create_article(self, client: OdooClient) -> Any:
        from vodoo.generic import create_record, delete_record

        self.article_id = create_record(
            client,
            "knowledge.article",
            {"name": "Vodoo Test Article", "body": "<p>Test article body</p>"},
        )
        yield
        with contextlib.suppress(Exception):
            delete_record(client, "knowledge.article", self.article_id)

    def test_list_articles(self, client: OdooClient) -> None:
        from vodoo.knowledge import list_articles

        articles = list_articles(client, domain=[["id", "=", self.article_id]])
        assert len(articles) == 1
        assert articles[0]["name"] == "Vodoo Test Article"

    def test_get_article(self, client: OdooClient) -> None:
        from vodoo.knowledge import get_article

        article = get_article(client, self.article_id)
        assert article["name"] == "Vodoo Test Article"

    def test_article_url(self, client: OdooClient) -> None:
        from vodoo.knowledge import get_article_url

        url = get_article_url(client, self.article_id)
        assert str(self.article_id) in url

    def test_article_comment(self, client: OdooClient) -> None:
        from vodoo.knowledge import add_comment, list_article_messages

        success = add_comment(
            client, self.article_id, "Article comment from vodoo", user_id=client.uid
        )
        assert success is True

        messages = list_article_messages(client, self.article_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Article comment from vodoo" in b for b in bodies)

    def test_article_note(self, client: OdooClient) -> None:
        from vodoo.knowledge import add_note

        success = add_note(client, self.article_id, "Article internal note", user_id=client.uid)
        assert success is True

    def test_article_attachments(self, client: OdooClient) -> None:
        from vodoo.knowledge import list_article_attachments

        attachments = list_article_attachments(client, self.article_id)
        assert isinstance(attachments, list)


# ══════════════════════════════════════════════════════════════════════════════
# Timer / Timesheet (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestTimer:
    """Test timer/timesheet operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    def _create_project_and_task(self, client: OdooClient) -> Any:
        from vodoo.generic import create_record, delete_record
        from vodoo.project import create_task

        self.project_id = create_record(
            client,
            "project.project",
            {"name": "Vodoo Timer Test Project", "allow_timesheets": True},
        )
        self.task_id = create_task(client, "Vodoo Timer Test Task", project_id=self.project_id)
        yield
        # Stop any running timers first
        with contextlib.suppress(Exception):
            from vodoo.timer import stop_active_timers

            stop_active_timers(client)
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                delete_record(client, model, rid)

    def test_start_stop_timer_on_task(self, client: OdooClient) -> None:
        from vodoo.timer import (
            fetch_active_timesheets,
            start_timer_on_task,
            stop_active_timers,
        )

        start_timer_on_task(client, self.task_id)

        active = fetch_active_timesheets(client)
        assert len(active) >= 1

        stopped = stop_active_timers(client)
        assert len(stopped) >= 1

    def test_today_timesheets(self, client: OdooClient) -> None:
        from vodoo.timer import fetch_today_timesheets, start_timer_on_task, stop_active_timers

        start_timer_on_task(client, self.task_id)
        try:
            timesheets = fetch_today_timesheets(client)
            assert len(timesheets) >= 1
        finally:
            stop_active_timers(client)


# ══════════════════════════════════════════════════════════════════════════════
# Exception hierarchy (live server)
# ══════════════════════════════════════════════════════════════════════════════


class TestExceptions:
    """Verify Vodoo exceptions are raised correctly against a real Odoo."""

    def test_record_not_found(self, client: OdooClient) -> None:
        """Reading a non-existent record must raise RecordNotFoundError."""
        from vodoo.base import get_record

        with pytest.raises(RecordNotFoundError) as exc_info:
            get_record(client, "res.partner", 999999999)

        assert exc_info.value.model == "res.partner"
        assert exc_info.value.record_id == 999999999

    def test_record_not_found_is_vodoo_error(self, client: OdooClient) -> None:
        """RecordNotFoundError must be catchable as VodooError."""
        from vodoo.base import get_record

        with pytest.raises(VodooError):
            get_record(client, "res.partner", 999999999)

    def test_access_error_on_forbidden_model(self, client: OdooClient) -> None:
        """Writing to a model without permission should raise a TransportError subclass.

        We create a share user with no groups, then try to write via that
        user's credentials.  The server should reject with an AccessError.
        """
        from vodoo.config import OdooConfig
        from vodoo.security import create_user

        user_id, password = create_user(
            client,
            name="Vodoo Exception Test User",
            login="vodoo-exc-test@example.com",
        )
        try:
            # Build a client authenticated as the unprivileged user
            unprivileged_config = OdooConfig(
                url=client.config.url,
                database=client.config.database,
                username="vodoo-exc-test@example.com",
                password=password,
            )
            unprivileged_client = OdooClient(unprivileged_config, auto_detect=False)

            # This user has no groups → should get AccessError on write
            with pytest.raises(TransportError) as exc_info:
                unprivileged_client.write("res.partner", [1], {"name": "Should Fail"})

            # Should be catchable via VodooError
            assert isinstance(exc_info.value, VodooError)
        finally:
            with contextlib.suppress(Exception):
                from vodoo.generic import delete_record

                delete_record(client, "res.users", user_id)

    def test_validation_error_on_bad_data(self, client: OdooClient) -> None:
        """Creating a record with invalid data should raise a TransportError.

        Duplicate login is a common way to trigger a server-side constraint.
        """
        # "admin" login already exists — creating another should violate
        # the unique constraint and raise a ValidationError or similar.
        with pytest.raises(TransportError):
            client.create(
                "res.users",
                {
                    "name": "Duplicate Admin",
                    "login": "admin",
                    "password": "test",
                },
            )
