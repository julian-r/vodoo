"""Provision least-privilege test users and audit the loaded registry, not production."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from vodoo.client import OdooClient
from vodoo.documents import DocumentNamespace
from vodoo.helpdesk import HelpdeskNamespace
from vodoo.knowledge import KnowledgeNamespace
from vodoo.task_context import _RELATION_MODELS, ATTACHMENT_FIELDS, CORE_FIELDS, MESSAGE_FIELDS

SERVICE_LOGIN = "vodoo-context-service"
ADMINISTRATIVE_GROUPS = ("base.group_system", "base.group_erp_manager", "base.group_user")


def provision_service_account(client: OdooClient, *, enterprise: bool) -> tuple[int, str]:
    """Use Vodoo's actual API groups without internal-user or administrator groups."""
    groups, _warnings = client.security.create_groups()
    wanted = ["API Base", "API Project"]
    if enterprise:
        wanted.extend(["API Knowledge", "API Helpdesk"])
    users = client.search("res.users", domain=[("login", "=", SERVICE_LOGIN)], limit=1)
    if users:
        user_id = users[0]
    else:
        user_id, _password = client.security.create_user("Vodoo context service", SERVICE_LOGIN)
    # Replace rather than add, so reused databases cannot retain privileged groups.
    client.write(
        "res.users",
        [user_id],
        {client.security._groups_field(): [(6, 0, [groups[name] for name in wanted])]},
    )
    user = client.security.get_user(user_id)
    assert user["share"] is True
    assigned = user[client.security._groups_field()]
    for xmlid in ADMINISTRATIVE_GROUPS:
        assert client.security._get_group_id_by_xmlid(xmlid) not in assigned, xmlid
    return user_id, SERVICE_LOGIN


def audit_projections() -> dict[str, list[str]]:
    """Explicit current projections, including Enterprise defaults and relation names."""
    return {
        **{model: ["id", "display_name"] for model in _RELATION_MODELS.values()},
        "project.task": list(dict.fromkeys([*CORE_FIELDS, *_RELATION_MODELS, "display_name"])),
        "mail.message": MESSAGE_FIELDS,
        "ir.attachment": ATTACHMENT_FIELDS,
        "knowledge.article": KnowledgeNamespace._default_fields,
        "helpdesk.ticket": HelpdeskNamespace._default_fields,
        "documents.document": DocumentNamespace._default_fields,
    }


def write_field_access_audit(path: Path, container: str, database: str, user_id: int) -> None:
    """Audit effective inherited field declarations using licensed installed source.

    Only field/group metadata is exported, never proprietary source or records.
    Model ACL failures are separate from field-group restrictions. The complete
    registry includes installed inherited overrides, not just base declarations.
    """
    projections = json.dumps(audit_projections())
    script = f"""\
import json
from odoo import release
projections = json.loads({projections!r})
user = env['res.users'].browse({user_id})
report = {{'odoo_version': release.version, 'models': {{}},
           'administrative_groups': dict((xmlid, user.with_user(user).has_group(xmlid))
                                         for xmlid in {ADMINISTRATIVE_GROUPS!r})}}
for model, requested in projections.items():
    if model not in env.registry:
        report['models'][model] = {{'installed': False}}
        continue
    records = env[model].with_user(user)
    readable = (records.has_access('read') if hasattr(records, 'has_access')
                else records.check_access_rights('read', raise_exception=False))
    metadata = records.fields_get(attributes=['type'])
    grouped = {{}}
    for name, field in records._fields.items():
        if not field.groups:
            continue
        groups = field.groups.split(',')
        category = ('system_admin_only' if groups == ['base.group_system'] else
                    'administrative_access' if 'base.group_erp_manager' in groups else
                    'other_field_groups')
        grouped[name] = {{'groups': groups, 'classification': category,
                         'accessible': name in metadata, 'requested': name in requested}}
    report['models'][model] = {{
        'installed': True, 'model_read_access': readable,
        'requested': requested, 'available_fields': sorted(metadata),
        'unavailable_requested': [name for name in requested if name not in metadata],
        'group_restricted_fields': grouped,
    }}
print('VODOO_FIELD_AUDIT=' + json.dumps(report, sort_keys=True))
"""
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "odoo",
            "shell",
            "-d",
            database,
            "--no-http",
            "-c",
            "/etc/odoo/odoo.conf",
            "--stop-after-init",
        ],
        input=script,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    report: dict[str, Any] | None = None
    for line in result.stdout.splitlines():
        if line.startswith("VODOO_FIELD_AUDIT="):
            report = json.loads(line.partition("=")[2])
    if report is None:
        raise RuntimeError("Odoo shell did not return the field access audit")
    image_id = subprocess.check_output(
        ["docker", "inspect", "--format", "{{.Image}}", container], text=True, timeout=10
    ).strip()
    labels = subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{json .Config.Labels}}", image_id],
        text=True,
        timeout=10,
    )
    report["source"] = {
        "image_id": image_id,
        "enterprise_provenance": {
            name: value
            for name, value in (json.loads(labels) or {}).items()
            if name.startswith("com.vodoo.enterprise.")
        },
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
