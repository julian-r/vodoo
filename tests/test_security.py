"""Focused tests for Vodoo security group definitions."""

from vodoo.security import GROUP_DEFINITIONS


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
