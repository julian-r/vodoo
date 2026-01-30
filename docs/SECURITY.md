# Security & Least-Privilege Service Accounts

Vodoo is designed to run with a dedicated service account that has only the access it needs. This minimizes risk and keeps automation actions isolated from human users.

## Recommended Setup (Summary)

1. **Create a dedicated user** in Odoo (e.g., `service-vodoo@company.com`).
2. **Remove `base.group_user` and `base.group_portal`** from the service account to avoid web UI access and portal field restrictions.
3. **Create a custom security group** (via module or RPC) and grant only the required `ir.model.access` permissions.
4. **Add record rules** to scope what the service account can access (e.g., only followed projects).
5. **Authenticate with a strong password or API key**, and rotate credentials on a schedule.

## CLI Utilities

Vodoo ships with helpers to bootstrap groups and assign a bot user:

```bash
# Create or reuse the standard Vodoo API groups
vodoo security create-groups

# Assign a bot user (by login) to all Vodoo API groups
vodoo security assign-bot --login service-vodoo@company.com

# Or by user ID
vodoo security assign-bot --user-id 42
```

By default, `assign-bot` removes `base.group_user` and `base.group_portal` before adding the API groups. Use `--keep-default-groups` if you want to preserve existing group memberships.

## Minimal Access Checklist

- ✅ `res.users`, `res.partner`, `res.company` (read-only) for lookups
- ✅ `mail.message`, `mail.followers`, `ir.attachment` for chatter and files
- ✅ Business models used by your workflow (helpdesk, project, CRM, knowledge)
- ✅ Record rules that limit access to the intended dataset

## Project Visibility Notes

For project data, the service account must be **a follower** of the relevant projects to read or create tasks when projects are configured for invited users only.

## Portal User Caveat

Avoid assigning `base.group_portal`: Odoo enforces portal-only field restrictions on models like `project.task`, which can break create/update flows.

## Notes on Comments

If you post public comments as a non-internal user, ensure Odoo’s `mail.message` subtype is **non-internal** (e.g., “Discussions”). Internal notes should use the internal subtype.

---

For deeper operational guidance, create model access rules via RPC or a small custom module and keep the service account’s permissions narrowly scoped to your workflows.
