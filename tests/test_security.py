"""Focused tests for Vodoo security group definitions."""

import subprocess
import sys

from vodoo.security import GROUP_DEFINITIONS


def test_generated_security_groups_can_be_imported_directly() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from vodoo.generated.security_groups import GROUP_DEFINITIONS; "
            "assert GROUP_DEFINITIONS",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_api_base_can_resolve_stable_message_subtype_external_ids() -> None:
    base_group = next(group for group in GROUP_DEFINITIONS if group.name == "API Base")
    model_data = next(entry for entry in base_group.access if entry.model == "ir.model.data")
    assert model_data.perm_read is True
    assert model_data.perm_write is False


def test_api_project_can_read_project_roles_without_modifying_them() -> None:
    project_group = next(group for group in GROUP_DEFINITIONS if group.name == "API Project")
    role_access = next(access for access in project_group.access if access.model == "project.role")

    assert (
        role_access.perm_read,
        role_access.perm_write,
        role_access.perm_create,
        role_access.perm_unlink,
    ) == (True, False, False, False)


def test_project_milestone_rule_uses_project_follower_boundary() -> None:
    project_group = next(group for group in GROUP_DEFINITIONS if group.name == "API Project")
    milestone_rule = next(rule for rule in project_group.rules if rule.model == "project.milestone")

    assert milestone_rule.domain == (
        "[('project_id.message_partner_ids', 'in', [user.partner_id.id])]"
    )
    assert (
        milestone_rule.perm_read,
        milestone_rule.perm_write,
        milestone_rule.perm_create,
        milestone_rule.perm_unlink,
    ) == (True, True, True, False)
