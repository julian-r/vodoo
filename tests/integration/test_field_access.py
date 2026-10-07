"""Context and effective field-access audits as provisioned API service accounts."""

from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from dotenv import dotenv_values
from typer.testing import CliRunner

from tests.integration.service_account import ADMINISTRATIVE_GROUPS
from vodoo.aio.client import AsyncOdooClient
from vodoo.client import OdooClient
from vodoo.config import OdooConfig
from vodoo.exceptions import OdooAccessError
from vodoo.main import app
from vodoo.task_context import ATTACHMENT_FIELDS, MESSAGE_FIELDS


@pytest.fixture(scope="module")
def service_config(odoo_config: OdooConfig) -> OdooConfig:
    path = Path(os.environ["VODOO_TEST_ENV"] + ".service")
    assert path.is_file(), "Provision the separate API service account with setup_odoo.py"
    values = dotenv_values(path)
    assert values["ODOO_URL"] == odoo_config.url
    assert values["ODOO_DATABASE"] == odoo_config.database
    return odoo_config.model_copy(
        update={"username": values["ODOO_USERNAME"], "password": values["ODOO_PASSWORD"]}
    )


@pytest.fixture(scope="module")
def service_client(service_config: OdooConfig) -> Iterator[OdooClient]:
    with OdooClient(service_config) as client:
        yield client


@pytest.fixture(scope="module")
def seed_record(client: OdooClient) -> Iterator[Callable[[str, dict[str, Any]], int]]:
    # Register each cleanup immediately, even if subsequent fixture setup fails.
    # ExitStack runs every callback even when one unlink raises.
    with ExitStack() as cleanup:

        def create(model: str, values: dict[str, Any]) -> int:
            record_id = client.create(model, values)
            cleanup.callback(client.unlink, model, [record_id])
            return record_id

        yield create


@pytest.fixture(scope="module")
def context_task(
    client: OdooClient,
    service_client: OdooClient,
    seed_record: Callable[[str, dict[str, Any]], int],
) -> dict[str, Any]:
    """Admin seeds data only in the disposable integration database."""
    user = client.security.get_user(service_client.uid)
    assert user["share"] is True
    for xmlid in ADMINISTRATIVE_GROUPS:
        assert (
            client.security._get_group_id_by_xmlid(xmlid)
            not in user[client.security._groups_field()]
        )
    project_id = seed_record("project.project", {"name": "Vodoo field-access project"})
    client.execute(
        "project.project", "message_subscribe", [project_id], partner_ids=[user["partner_id"][0]]
    )
    stage_id = seed_record(
        "project.task.type",
        {
            "name": "Vodoo tracked stage",
            "user_id": False,
            "project_ids": [(6, 0, [project_id])],
        },
    )
    task_id = seed_record(
        "project.task",
        {"name": "Vodoo field-access task", "project_id": project_id, "stage_id": False},
    )
    client.write("project.task", [task_id], {"stage_id": stage_id})
    attachments = [
        seed_record(
            "ir.attachment",
            {
                "name": "context.txt",
                "type": "binary",
                "mimetype": "text/plain",
                "datas": base64.b64encode(b"test context").decode(),
                "public": True,
                "res_model": model,
                "res_id": record_id,
            },
        )
        for model, record_id in [("project.task", task_id), ("res.partner", user["partner_id"][0])]
    ]
    subtype = client.search_read(
        "ir.model.data",
        domain=[("module", "=", "mail"), ("name", "=", "mt_comment")],
        fields=["res_id"],
        limit=1,
    )[0]["res_id"]
    message_ids = [
        seed_record(
            "mail.message",
            {
                "model": "project.task",
                "res_id": task_id,
                "body": body,
                "message_type": "comment",
                "subtype_id": subtype,
                "attachment_ids": [(6, 0, attachments)],
            },
        )
        for body in ("<p>Readable comment</p>", "")
    ]
    return {"task_id": task_id, "attachments": attachments, "messages": message_ids}


def _assert_service_context(result: dict[str, Any], fixture: dict[str, Any]) -> None:
    assert result["task"]["id"] == fixture["task_id"]
    assert result["complete"] is False
    assert all(status["complete"] for status in result["pagination"].values())
    assert result["errors"] == [
        {
            "section": "messages",
            "type": "unsupported_fields",
            "message": "Fields unavailable on this server or to this user",
            "fields": ["tracking_value_ids"],
        }
    ]
    messages = {row["id"]: row for row in result["messages"]}
    assert set(fixture["messages"]) <= messages.keys()
    assert messages[fixture["messages"][1]]["body"] in ("", False)
    assert all("tracking_value_ids" not in row for row in messages.values())
    assert set(fixture["attachments"]) <= {row["id"] for row in result["attachments"]}
    assert all(set(ATTACHMENT_FIELDS) <= row.keys() for row in result["attachments"])


def test_service_account_context_and_denied_tracking(
    service_client: OdooClient, context_task: dict[str, Any]
) -> None:
    fields = service_client.fields_get("mail.message", attributes=["type"])
    assert "tracking_value_ids" not in fields
    assert "attachment_ids" in fields
    with pytest.raises(OdooAccessError):
        service_client.read("mail.message", context_task["messages"], fields=MESSAGE_FIELDS)
    result = service_client.tasks.context(context_task["task_id"], page_size=1)
    _assert_service_context(result, context_task)
    # A real service-account context payload goes through the actual CLI command.
    with patch("vodoo.main.get_client", return_value=service_client):
        cli = CliRunner().invoke(
            app,
            ["--json", "project-task", "context", str(context_task["task_id"]), "--page-size", "1"],
        )
    assert cli.exit_code == 1
    _assert_service_context(json.loads(cli.stdout), context_task)


def test_admin_context_retains_tracking_ids(
    client: OdooClient, context_task: dict[str, Any]
) -> None:
    result = client.tasks.context(context_task["task_id"], page_size=1)
    assert result["complete"] is True, result["errors"]
    assert any(message["tracking_value_ids"] for message in result["messages"])
    assert set(context_task["messages"]) <= {row["id"] for row in result["messages"]}


def test_async_service_account_context(
    service_config: OdooConfig, context_task: dict[str, Any]
) -> None:
    async def run() -> dict[str, Any]:
        async with AsyncOdooClient(service_config) as client:
            return await client.tasks.context(context_task["task_id"], page_size=1)

    _assert_service_context(asyncio.run(run()), context_task)


def test_effective_inherited_field_audit(is_enterprise: bool) -> None:
    """Audit group restrictions separately from model ACLs and missing modules."""
    path = Path(os.environ["VODOO_TEST_ENV"] + ".audit.json")
    assert path.is_file(), "setup_odoo.py must audit the actual loaded registry"
    audit = json.loads(path.read_text())
    assert audit["source"]["image_id"].startswith("sha256:")
    if is_enterprise:
        assert audit["source"]["enterprise_provenance"]["com.vodoo.enterprise.revision"]
    assert not any(audit["administrative_groups"].values())
    models = audit["models"]
    tracking = models["mail.message"]["group_restricted_fields"]["tracking_value_ids"]
    assert tracking["classification"] == "system_admin_only"
    assert tracking["accessible"] is False
    assert models["mail.message"]["model_read_access"] is True
    assert models["project.task"]["model_read_access"] is True
    assert models["ir.attachment"]["model_read_access"] is True
    for model in ("knowledge.article", "helpdesk.ticket", "documents.document"):
        assert models[model]["installed"] is is_enterprise
        if is_enterprise:
            # Missing model permission is not evidence of an admin-only field.
            assert isinstance(models[model]["model_read_access"], bool)
            assert "group_restricted_fields" in models[model]
            if model != "documents.document":
                assert models[model]["model_read_access"] is True
            forbidden_defaults = [
                name
                for name, field in models[model]["group_restricted_fields"].items()
                if field["requested"]
                and not field["accessible"]
                and field["classification"] in {"system_admin_only", "administrative_access"}
            ]
            assert not forbidden_defaults, (model, forbidden_defaults)
    # Export metadata to pytest/JUnit logs; never export company records or source.
    print(json.dumps(audit, sort_keys=True))
