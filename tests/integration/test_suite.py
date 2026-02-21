"""Integration tests for vodoo against a live Odoo instance.

Community tests (project, project-task, crm, model, security) run on all versions.
Enterprise tests (helpdesk, knowledge, timer) require the enterprise flag.
"""

import contextlib
import tempfile
import time
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


def _model_exists(client: OdooClient, model_name: str) -> bool:
    models = client.search_read(
        "ir.model",
        domain=[["model", "=", model_name]],
        fields=["id"],
        limit=1,
    )
    return bool(models)


def _ensure_module_installed(client: OdooClient, module_name: str) -> bool:
    modules = client.search_read(
        "ir.module.module",
        domain=[["name", "=", module_name]],
        fields=["id", "state"],
        limit=1,
    )
    if not modules:
        return False

    module = modules[0]
    if module.get("state") == "installed":
        return True

    client.execute("ir.module.module", "button_immediate_install", [module["id"]])

    for _ in range(60):
        state_rows = client.search_read(
            "ir.module.module",
            domain=[["id", "=", module["id"]]],
            fields=["state"],
            limit=1,
        )
        state = state_rows[0].get("state") if state_rows else None
        if state == "installed":
            return True
        time.sleep(1)

    return False


def _create_account_move_for_tests(client: OdooClient) -> int:
    """Create a draft account.move for integration tests, or skip if unavailable."""
    try:
        if not _model_exists(client, "account.move"):
            installed = _ensure_module_installed(client, "account")
            if not installed or not _model_exists(client, "account.move"):
                pytest.skip("account.move model is not available in this test database")

        journals = client.search_read(
            "account.journal",
            domain=[["type", "=", "general"]],
            fields=["id", "default_account_id"],
            limit=1,
        )
        if not journals:
            pytest.skip("No general journal found; accounting module may not be configured")

        journal = journals[0]
        default_account = journal.get("default_account_id")
        candidate_ids: list[int] = []
        if isinstance(default_account, list):
            candidate_ids.append(default_account[0])

        accounts = client.search_read(
            "account.account",
            domain=[],
            fields=["id"],
            limit=50,
        )
        candidate_ids.extend(int(a["id"]) for a in accounts)

        seen: set[int] = set()
        last_exc: Exception | None = None

        for account_id in candidate_ids:
            if account_id in seen:
                continue
            seen.add(account_id)

            values = {
                "move_type": "entry",
                "journal_id": journal["id"],
                "line_ids": [
                    (0, 0, {"name": "Vodoo debit", "account_id": account_id, "debit": 1.0}),
                    (0, 0, {"name": "Vodoo credit", "account_id": account_id, "credit": 1.0}),
                ],
            }
            try:
                return client.generic.create("account.move", values)
            except Exception as exc:  # pragma: no cover - depends on chart config
                last_exc = exc
                continue

        detail = f": {last_exc}" if last_exc else ""
        pytest.skip(f"Could not create account.move for tests{detail}")
    except Exception as exc:
        pytest.skip(f"Skipping account.move integration tests: {exc}")


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
        # Create
        rid = client.generic.create(
            "res.partner",
            {"name": "Vodoo Test Partner", "email": "vodoo-test@example.com"},
        )
        assert rid > 0

        # Read
        records = client.generic.search("res.partner", domain=[["id", "=", rid]])
        assert len(records) == 1
        assert records[0]["name"] == "Vodoo Test Partner"

        # Update
        assert client.generic.update("res.partner", rid, {"phone": "+1-555-0199"}) is True
        records = client.generic.search("res.partner", domain=[["id", "=", rid]], fields=["phone"])
        assert records[0]["phone"] == "+1-555-0199"

        # Delete
        assert client.generic.delete("res.partner", rid) is True
        assert client.generic.search("res.partner", domain=[["id", "=", rid]]) == []

    def test_call_method(self, client: OdooClient) -> None:
        result = client.generic.call("res.partner", "name_search", args=["Administrator"])
        assert isinstance(result, list)

    def test_search_with_limit_and_order(self, client: OdooClient) -> None:
        records = client.generic.search(
            "res.partner", limit=3, order="id asc", fields=["id", "name"]
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
        self.project_id = client.generic.create("project.project", {"name": "Vodoo Test Project"})
        yield
        with contextlib.suppress(Exception):
            client.generic.delete("project.project", self.project_id)

    def test_list_projects(self, client: OdooClient) -> None:
        projects = client.projects.list(domain=[["id", "=", self.project_id]])
        assert len(projects) == 1
        assert projects[0]["name"] == "Vodoo Test Project"

    def test_get_project(self, client: OdooClient) -> None:
        project = client.projects.get(self.project_id)
        assert project["name"] == "Vodoo Test Project"

    def test_set_project_fields(self, client: OdooClient) -> None:
        client.projects.set(self.project_id, {"description": "<p>Updated</p>"})
        project = client.projects.get(self.project_id)
        assert "Updated" in str(project.get("description", ""))

    def test_list_project_fields(self, client: OdooClient) -> None:
        fields = client.projects.fields()
        assert "name" in fields
        assert "user_id" in fields

    def test_project_url(self, client: OdooClient) -> None:
        url = client.projects.url(self.project_id)
        assert str(self.project_id) in url
        assert "project.project" in url or "/web#" in url

    def test_project_comment(self, client: OdooClient) -> None:
        success = client.projects.comment(
            self.project_id, "Test comment from vodoo", user_id=client.uid
        )
        assert success is True

        messages = client.projects.messages(self.project_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Test comment from vodoo" in b for b in bodies)

    def test_project_note(self, client: OdooClient) -> None:
        success = client.projects.note(
            self.project_id, "Internal note from vodoo", user_id=client.uid
        )
        assert success is True

    def test_project_attachment(self, client: OdooClient) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = client.projects.attach(self.project_id, tmp_path)
            assert att_id > 0

            attachments = client.projects.attachments(self.project_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_list_stages(self, client: OdooClient) -> None:
        stages = client.projects.stages()
        assert isinstance(stages, list)


# ══════════════════════════════════════════════════════════════════════════════
# Project Tasks (project.task)
# ══════════════════════════════════════════════════════════════════════════════


class TestProjectTask:
    """Test project.task operations."""

    @pytest.fixture(autouse=True)
    def _create_project_and_task(self, client: OdooClient) -> Any:
        self.project_id = client.generic.create(
            "project.project", {"name": "Vodoo Task Test Project"}
        )
        self.task_id = client.tasks.create("Vodoo Test Task", project_id=self.project_id)
        yield
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                client.generic.delete(model, rid)

    def test_list_tasks(self, client: OdooClient) -> None:
        tasks = client.tasks.list(domain=[["id", "=", self.task_id]])
        assert len(tasks) == 1
        assert tasks[0]["name"] == "Vodoo Test Task"

    def test_get_task(self, client: OdooClient) -> None:
        task = client.tasks.get(self.task_id)
        assert task["name"] == "Vodoo Test Task"

    def test_set_task_fields(self, client: OdooClient) -> None:
        client.tasks.set(self.task_id, {"priority": "1"})
        task = client.tasks.get(self.task_id, fields=["priority"])
        assert task["priority"] == "1"

    def test_list_task_fields(self, client: OdooClient) -> None:
        fields = client.tasks.fields()
        assert "name" in fields
        assert "project_id" in fields
        assert "stage_id" in fields

    def test_task_url(self, client: OdooClient) -> None:
        url = client.tasks.url(self.task_id)
        assert str(self.task_id) in url

    def test_task_comment(self, client: OdooClient) -> None:
        success = client.tasks.comment(self.task_id, "Task comment from vodoo", user_id=client.uid)
        assert success is True

        messages = client.tasks.messages(self.task_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Task comment from vodoo" in b for b in bodies)

    def test_task_note(self, client: OdooClient) -> None:
        success = client.tasks.note(self.task_id, "Task internal note", user_id=client.uid)
        assert success is True

    def test_task_attachment(self, client: OdooClient) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"task attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = client.tasks.attach(self.task_id, tmp_path)
            assert att_id > 0

            attachments = client.tasks.attachments(self.task_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_download_attachment(self, client: OdooClient) -> None:
        from vodoo.base import download_attachment

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"download test content")
            tmp_path = Path(f.name)

        try:
            att_id = client.tasks.attach(self.task_id, tmp_path)

            with tempfile.TemporaryDirectory() as outdir:
                out = download_attachment(client, att_id, Path(outdir) / "downloaded.txt")
                assert out.exists()
                assert out.read_bytes() == b"download test content"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_create_attachment_from_bytes(self, client: OdooClient) -> None:
        from vodoo.base import create_attachment, download_attachment, list_attachments

        content = b"bytes upload integration test content"
        att_id = create_attachment(
            client,
            "project.task",
            self.task_id,
            data=content,
            name="bytes_test.txt",
        )
        try:
            assert isinstance(att_id, int)
            assert att_id > 0

            attachments = list_attachments(client, "project.task", self.task_id)
            assert any(a["id"] == att_id for a in attachments)

            with tempfile.TemporaryDirectory() as outdir:
                out = download_attachment(client, att_id, Path(outdir) / "bytes_test.txt")
                assert out.exists()
                assert out.read_bytes() == content
        finally:
            with contextlib.suppress(Exception):
                client.generic.delete("ir.attachment", att_id)

    def test_get_attachment_data(self, client: OdooClient) -> None:
        from vodoo.base import get_attachment_data

        content = b"get_attachment_data test content"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            att_id = client.tasks.attach(self.task_id, tmp_path)
            data = get_attachment_data(client, att_id)
            assert data == content
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_record_attachment_data(self, client: OdooClient) -> None:
        from vodoo.base import get_record_attachment_data

        content = b"get_record_attachment_data test content"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            client.tasks.attach(self.task_id, tmp_path)
            result = get_record_attachment_data(client, "project.task", self.task_id)
            assert isinstance(result, list)
            assert len(result) >= 1
            for att_id, name, data in result:
                assert isinstance(att_id, int)
                assert isinstance(name, str)
                assert isinstance(data, bytes)
            assert any(data == content for _, _, data in result)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_create_task_with_options(self, client: OdooClient) -> None:
        task_id = client.tasks.create(
            "Task With Description",
            project_id=self.project_id,
            description="<p>Some description</p>",
        )
        try:
            task = client.tasks.get(task_id)
            assert "Some description" in str(task.get("description", ""))
        finally:
            client.generic.delete("project.task", task_id)

    def test_tags_crud(self, client: OdooClient) -> None:
        # Create tag
        tag_id = client.tasks.create_tag("vodoo-test-tag")
        assert tag_id > 0

        try:
            # List tags
            tags = client.tasks.tags()
            assert any(t["id"] == tag_id for t in tags)

            # Add tag to task
            client.tasks.add_tag(self.task_id, tag_id)

            # Verify
            task = client.tasks.get(self.task_id, fields=["tag_ids"])
            tag_ids = task.get("tag_ids", [])
            assert tag_id in tag_ids
        finally:
            client.tasks.delete_tag(tag_id)

    def test_subtask(self, client: OdooClient) -> None:
        sub_id = client.tasks.create(
            "Vodoo Subtask", project_id=self.project_id, parent_id=self.task_id
        )
        try:
            sub = client.tasks.get(sub_id, fields=["parent_id"])
            parent = sub.get("parent_id")
            if isinstance(parent, list):
                assert parent[0] == self.task_id
            else:
                assert parent == self.task_id
        finally:
            client.generic.delete("project.task", sub_id)


# ══════════════════════════════════════════════════════════════════════════════
# CRM (crm.lead)
# ══════════════════════════════════════════════════════════════════════════════


class TestCRM:
    """Test CRM lead/opportunity operations."""

    @pytest.fixture(autouse=True)
    def _create_lead(self, client: OdooClient) -> Any:
        self.lead_id = client.generic.create(
            "crm.lead",
            {
                "name": "Vodoo Test Lead",
                "email_from": "lead-test@example.com",
                "type": "opportunity",
            },
        )
        yield
        with contextlib.suppress(Exception):
            client.generic.delete("crm.lead", self.lead_id)

    def test_list_leads(self, client: OdooClient) -> None:
        leads = client.crm.list(domain=[["id", "=", self.lead_id]])
        assert len(leads) == 1
        assert leads[0]["name"] == "Vodoo Test Lead"

    def test_get_lead(self, client: OdooClient) -> None:
        lead = client.crm.get(self.lead_id)
        assert lead["name"] == "Vodoo Test Lead"
        assert lead["email_from"] == "lead-test@example.com"

    def test_set_lead_fields(self, client: OdooClient) -> None:
        client.crm.set(self.lead_id, {"phone": "+1-555-0100"})
        lead = client.crm.get(self.lead_id, fields=["phone"])
        assert lead["phone"] == "+1-555-0100"

    def test_list_lead_fields(self, client: OdooClient) -> None:
        fields = client.crm.fields()
        assert "name" in fields
        assert "stage_id" in fields
        assert "email_from" in fields

    def test_lead_url(self, client: OdooClient) -> None:
        url = client.crm.url(self.lead_id)
        assert str(self.lead_id) in url

    def test_lead_comment(self, client: OdooClient) -> None:
        success = client.crm.comment(self.lead_id, "Lead comment from vodoo", user_id=client.uid)
        assert success is True

        messages = client.crm.messages(self.lead_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Lead comment from vodoo" in b for b in bodies)

    def test_lead_note(self, client: OdooClient) -> None:
        success = client.crm.note(self.lead_id, "Lead internal note", user_id=client.uid)
        assert success is True

    def test_lead_attachment(self, client: OdooClient) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"lead attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = client.crm.attach(self.lead_id, tmp_path)
            assert att_id > 0

            attachments = client.crm.attachments(self.lead_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_lead_tags(self, client: OdooClient) -> None:
        tag_id = client.generic.create("crm.tag", {"name": "vodoo-crm-test-tag"})
        try:
            tags = client.crm.tags()
            assert any(t["id"] == tag_id for t in tags)

            client.crm.add_tag(self.lead_id, tag_id)

            lead = client.crm.get(self.lead_id, fields=["tag_ids"])
            assert tag_id in lead.get("tag_ids", [])
        finally:
            client.generic.delete("crm.tag", tag_id)

    def test_download_all_attachments(self, client: OdooClient) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-fake-content")
            tmp_path = Path(f.name)

        try:
            client.crm.attach(self.lead_id, tmp_path)

            with tempfile.TemporaryDirectory() as outdir:
                downloaded = client.crm.download(self.lead_id, Path(outdir))
                assert len(downloaded) >= 1
        finally:
            tmp_path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Accounting (account.move)
# ══════════════════════════════════════════════════════════════════════════════


class TestAccountMove:
    """Test account.move namespace and attachment workflow."""

    @pytest.fixture(autouse=True)
    def _create_account_move(self, client: OdooClient) -> Any:
        self.move_id = _create_account_move_for_tests(client)
        yield
        with contextlib.suppress(Exception):
            client.generic.delete("account.move", self.move_id)

    def test_list_account_moves(self, client: OdooClient) -> None:
        moves = client.account_moves.list(domain=[["id", "=", self.move_id]])
        assert len(moves) == 1
        assert moves[0]["id"] == self.move_id

    def test_account_move_url(self, client: OdooClient) -> None:
        url = client.account_moves.url(self.move_id)
        assert str(self.move_id) in url

    def test_account_move_attachment(self, client: OdooClient) -> None:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-account-move-test")
            tmp_path = Path(f.name)

        try:
            att_id = client.account_moves.attach(self.move_id, tmp_path)
            assert att_id > 0

            attachments = client.account_moves.attachments(self.move_id)
            assert any(a["id"] == att_id for a in attachments)

            with tempfile.TemporaryDirectory() as outdir:
                downloaded = client.account_moves.download(
                    self.move_id,
                    Path(outdir),
                    extension="pdf",
                )
                assert len(downloaded) >= 1
        finally:
            tmp_path.unlink(missing_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
# Security
# ══════════════════════════════════════════════════════════════════════════════


class TestSecurity:
    """Test security group utilities."""

    def test_create_security_groups(self, client: OdooClient) -> None:
        group_ids, _warnings = client.security.create_groups()
        assert len(group_ids) > 0
        # Should be idempotent
        group_ids2, _ = client.security.create_groups()
        assert group_ids == group_ids2

    def test_create_user(self, client: OdooClient) -> None:
        user_id, _password = client.security.create_user(
            name="Vodoo Test Bot",
            login="vodoo-bot@example.com",
            password="TestPassword123",
        )
        try:
            assert user_id > 0
            info = client.security.get_user(user_id)
            assert info["login"] == "vodoo-bot@example.com"
            assert info["name"] == "Vodoo Test Bot"
        finally:
            with contextlib.suppress(Exception):
                client.generic.delete("res.users", user_id)

    def test_resolve_user_id(self, client: OdooClient) -> None:
        uid = client.security.resolve_user(user_id=None, login="admin")
        assert uid > 0

    def test_set_user_password(self, client: OdooClient) -> None:
        user_id, _ = client.security.create_user(
            name="Vodoo PW Test",
            login="vodoo-pw-test@example.com",
        )
        try:
            new_pw = client.security.set_password(user_id, "NewPassword456")
            assert new_pw == "NewPassword456"

            # Also test generated password
            gen_pw = client.security.set_password(user_id)
            assert len(gen_pw) > 8
        finally:
            with contextlib.suppress(Exception):
                client.generic.delete("res.users", user_id)

    def test_assign_bot_to_groups(self, client: OdooClient) -> None:
        group_ids, _ = client.security.create_groups()
        user_id, _ = client.security.create_user(
            name="Vodoo Group Test",
            login="vodoo-group-test@example.com",
        )
        try:
            client.security.assign(user_id, list(group_ids.values()), remove_default_groups=True)
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
                client.generic.delete("res.users", user_id)


# ══════════════════════════════════════════════════════════════════════════════
# Helpdesk (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestHelpdesk:
    """Test helpdesk.ticket operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    def _create_ticket(self, client: OdooClient) -> Any:
        # Helpdesk needs a team; find or create one
        teams = client.search_read("helpdesk.team", limit=1, fields=["id"])
        if teams:
            self.team_id = teams[0]["id"]
        else:
            self.team_id = client.generic.create("helpdesk.team", {"name": "Vodoo Test Team"})

        self.ticket_id = client.generic.create(
            "helpdesk.ticket",
            {"name": "Vodoo Test Ticket", "team_id": self.team_id},
        )
        yield
        with contextlib.suppress(Exception):
            client.generic.delete("helpdesk.ticket", self.ticket_id)

    def test_list_tickets(self, client: OdooClient) -> None:
        tickets = client.helpdesk.list(domain=[["id", "=", self.ticket_id]])
        assert len(tickets) == 1
        assert tickets[0]["name"] == "Vodoo Test Ticket"

    def test_get_ticket(self, client: OdooClient) -> None:
        ticket = client.helpdesk.get(self.ticket_id)
        assert ticket["name"] == "Vodoo Test Ticket"

    def test_set_ticket_fields(self, client: OdooClient) -> None:
        client.helpdesk.set(self.ticket_id, {"priority": "2"})
        ticket = client.helpdesk.get(self.ticket_id, fields=["priority"])
        assert ticket["priority"] == "2"

    def test_list_ticket_fields(self, client: OdooClient) -> None:
        fields = client.helpdesk.fields()
        assert "name" in fields
        assert "team_id" in fields

    def test_ticket_url(self, client: OdooClient) -> None:
        url = client.helpdesk.url(self.ticket_id)
        assert str(self.ticket_id) in url

    def test_ticket_comment(self, client: OdooClient) -> None:
        success = client.helpdesk.comment(
            self.ticket_id, "Ticket comment from vodoo", user_id=client.uid
        )
        assert success is True

        messages = client.helpdesk.messages(self.ticket_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Ticket comment from vodoo" in b for b in bodies)

    def test_ticket_note(self, client: OdooClient) -> None:
        success = client.helpdesk.note(self.ticket_id, "Ticket internal note", user_id=client.uid)
        assert success is True

    def test_ticket_attachment(self, client: OdooClient) -> None:
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"ticket attachment content")
            tmp_path = Path(f.name)

        try:
            att_id = client.helpdesk.attach(self.ticket_id, tmp_path)
            assert att_id > 0

            attachments = client.helpdesk.attachments(self.ticket_id)
            assert any(a["id"] == att_id for a in attachments)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_ticket_attachment_from_bytes(self, client: OdooClient) -> None:
        att_id = client.helpdesk.attach(self.ticket_id, data=b"bytes upload test", name="test.txt")
        assert isinstance(att_id, int)
        assert att_id > 0

        attachments = client.helpdesk.attachments(self.ticket_id)
        assert any(a["id"] == att_id for a in attachments)

    def test_get_ticket_attachment_data(self, client: OdooClient) -> None:
        content = b"attachment bytes test content"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            att_id = client.helpdesk.attach(self.ticket_id, tmp_path)
            data = client.helpdesk.attachment_data(att_id)
            assert data == content
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_get_ticket_attachments_data(self, client: OdooClient) -> None:
        content = b"attachments data test content"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            tmp_path = Path(f.name)

        try:
            client.helpdesk.attach(self.ticket_id, tmp_path)
            result = client.helpdesk.all_attachment_data(self.ticket_id)
            assert isinstance(result, list)
            assert len(result) >= 1
            for att_id, name, data in result:
                assert isinstance(att_id, int)
                assert isinstance(name, str)
                assert isinstance(data, bytes)
            assert any(data == content for _, _, data in result)
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_ticket_tags(self, client: OdooClient) -> None:
        tag_id = client.generic.create("helpdesk.tag", {"name": "vodoo-helpdesk-test-tag"})
        try:
            tags = client.helpdesk.tags()
            assert any(t["id"] == tag_id for t in tags)

            client.helpdesk.add_tag(self.ticket_id, tag_id)
            ticket = client.helpdesk.get(self.ticket_id, fields=["tag_ids"])
            assert tag_id in ticket.get("tag_ids", [])
        finally:
            client.generic.delete("helpdesk.tag", tag_id)

    def test_create_ticket(self, client: OdooClient) -> None:
        ticket_id = client.helpdesk.create(
            "Vodoo Create Test Ticket",
            team_id=self.team_id,
            description="<p>Test description</p>",
        )
        try:
            assert ticket_id > 0
            ticket = client.helpdesk.get(ticket_id)
            assert ticket["name"] == "Vodoo Create Test Ticket"
            assert "Test description" in str(ticket.get("description", ""))
        finally:
            with contextlib.suppress(Exception):
                client.generic.delete("helpdesk.ticket", ticket_id)

    def test_create_ticket_with_tags(self, client: OdooClient) -> None:
        tag_id = client.generic.create("helpdesk.tag", {"name": "vodoo-create-test-tag"})
        ticket_id = None
        try:
            ticket_id = client.helpdesk.create(
                "Vodoo Tag Test Ticket",
                team_id=self.team_id,
                tag_ids=[tag_id],
            )
            assert ticket_id > 0
            ticket = client.helpdesk.get(ticket_id, fields=["tag_ids"])
            assert tag_id in ticket.get("tag_ids", [])
        finally:
            if ticket_id is not None:
                with contextlib.suppress(Exception):
                    client.generic.delete("helpdesk.ticket", ticket_id)
            with contextlib.suppress(Exception):
                client.generic.delete("helpdesk.tag", tag_id)


# ══════════════════════════════════════════════════════════════════════════════
# Knowledge (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestKnowledge:
    """Test knowledge.article operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    def _create_article(self, client: OdooClient) -> Any:
        self.article_id = client.generic.create(
            "knowledge.article",
            {"name": "Vodoo Test Article", "body": "<p>Test article body</p>"},
        )
        yield
        with contextlib.suppress(Exception):
            client.generic.delete("knowledge.article", self.article_id)

    def test_list_articles(self, client: OdooClient) -> None:
        articles = client.knowledge.list(domain=[["id", "=", self.article_id]])
        assert len(articles) == 1
        assert articles[0]["name"] == "Vodoo Test Article"

    def test_get_article(self, client: OdooClient) -> None:
        article = client.knowledge.get(self.article_id)
        assert article["name"] == "Vodoo Test Article"

    def test_article_url(self, client: OdooClient) -> None:
        url = client.knowledge.url(self.article_id)
        assert str(self.article_id) in url

    def test_article_comment(self, client: OdooClient) -> None:
        success = client.knowledge.comment(
            self.article_id, "Article comment from vodoo", user_id=client.uid
        )
        assert success is True

        messages = client.knowledge.messages(self.article_id)
        bodies = [m.get("body", "") for m in messages]
        assert any("Article comment from vodoo" in b for b in bodies)

    def test_article_note(self, client: OdooClient) -> None:
        success = client.knowledge.note(
            self.article_id, "Article internal note", user_id=client.uid
        )
        assert success is True

    def test_article_attachments(self, client: OdooClient) -> None:
        attachments = client.knowledge.attachments(self.article_id)
        assert isinstance(attachments, list)


# ══════════════════════════════════════════════════════════════════════════════
# Timer / Timesheet (enterprise only)
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.enterprise
class TestTimer:
    """Test timer/timesheet operations — requires enterprise edition."""

    @pytest.fixture(autouse=True)
    def _create_project_and_task(self, client: OdooClient) -> Any:
        self.project_id = client.generic.create(
            "project.project",
            {"name": "Vodoo Timer Test Project", "allow_timesheets": True},
        )
        self.task_id = client.tasks.create("Vodoo Timer Test Task", project_id=self.project_id)
        yield
        # Stop any running timers first
        with contextlib.suppress(Exception):
            client.timer.stop()
        for model, rid in [
            ("project.task", self.task_id),
            ("project.project", self.project_id),
        ]:
            with contextlib.suppress(Exception):
                client.generic.delete(model, rid)

    def test_start_stop_timer_on_task(self, client: OdooClient) -> None:
        client.timer.start_task(self.task_id)

        active = client.timer.active()
        assert len(active) >= 1

        stopped = client.timer.stop()
        assert len(stopped) >= 1

    def test_list_timesheets(self, client: OdooClient) -> None:
        client.timer.start_task(self.task_id)
        try:
            timesheets = client.timer.list()
            assert len(timesheets) >= 1
        finally:
            client.timer.stop()

    def test_handle_returns_from_start_task(self, client: OdooClient) -> None:
        """start_task() returns a TimerHandle."""
        handle = client.timer.start_task(self.task_id)
        try:
            assert handle is not None
            assert handle._source_kind == "task"
            assert handle._source_id == self.task_id
        finally:
            client.timer.stop()

    def test_handle_stop_stops_only_target(self, client: OdooClient) -> None:
        """TimerHandle.stop() stops only the timer it started."""
        handle = client.timer.start_task(self.task_id)

        active_before = client.timer.active()
        assert any(
            ts.source.kind == "task" and ts.source.id == self.task_id for ts in active_before
        )

        handle.stop()

        active_after = client.timer.active()
        assert not any(
            ts.source.kind == "task" and ts.source.id == self.task_id for ts in active_after
        )

    def test_handle_stop_raises_when_not_running(self, client: OdooClient) -> None:
        """TimerHandle.stop() raises ValueError if the timer is no longer active."""
        handle = client.timer.start_task(self.task_id)
        handle.stop()

        with pytest.raises(ValueError, match="No running timer found"):
            handle.stop()


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

        user_id, password = client.security.create_user(
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
                client.generic.delete("res.users", user_id)

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
