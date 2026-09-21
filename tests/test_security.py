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
