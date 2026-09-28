# Security & Least-Privilege Service Accounts

Vodoo is designed to run with a dedicated service account that has only the access it needs. This minimizes risk and keeps automation actions isolated from human users.

## Quick Start (Best Practice)

```bash
# 1. Create a new bot user with all Vodoo API groups (requires admin)
ODOO_USERNAME=admin@example.com ODOO_PASSWORD=... \
vodoo security create-user "Vodoo Bot" bot@company.com --assign-groups

# Output:
# Created user: Vodoo Bot (id=42)
# Login: bot@company.com
# Password: BCgXQ7d*tYxjArk2$7vHl2t*  <-- SAVE THIS!
# Share (not billed): True
# Assigned to 5 groups:
#   - API Base
#   - API CRM
#   - API Project
#   - API Knowledge
#   - API Helpdesk

# 2. Configure vodoo to use the new bot
cat > .env << EOF
ODOO_URL=https://your-instance.odoo.com
ODOO_DATABASE=your-database
ODOO_USERNAME=bot@company.com
ODOO_PASSWORD=BCgXQ7d*tYxjArk2$7vHl2t*
EOF

# 3. Add bot as follower to projects (for project access)
# See "Project Visibility" section below
```

## CLI Commands

### Create a Service Account

```bash
# Basic (generates password)
vodoo security create-user "Bot Name" bot@company.com

# With specific password
vodoo security create-user "Bot Name" bot@company.com --password MySecretPass123

# With all Vodoo API groups assigned
vodoo security create-user "Bot Name" bot@company.com --assign-groups

# Without groups (add manually later)
vodoo security create-user "Bot Name" bot@company.com
```

**Note:** Requires admin credentials (Access Rights group).

### Create Security Groups

```bash
# Create all Vodoo API groups (idempotent)
vodoo security create-groups
```

Creates these modular groups:

| Group | Purpose |
|-------|---------|
| **API Base** | Core access (required for all bots) |
| **API CRM** | CRM leads and opportunities |
| **API Project** | Projects and tasks |
| **API Knowledge** | Knowledge base articles |
| **API Helpdesk** | Helpdesk tickets |

### Assign Groups to Existing User

```bash
# Assign all groups
vodoo security assign-bot --login bot@company.com

# By user ID
vodoo security assign-bot --user-id 42

# Keep existing groups (don't remove base.group_user/portal)
vodoo security assign-bot --login bot@company.com --keep-default-groups
```

### Set or Reset Password

```bash
# Generate new password
vodoo security set-password --login bot@company.com

# Set specific password
vodoo security set-password --login bot@company.com --password MyNewPassword123

# By user ID
vodoo security set-password --user-id 42
```

**Note:** Requires admin credentials.

## Passwords, API Keys, and Transport Selection

`ODOO_PASSWORD` accepts either the account password or an API key, but they are not transport-equivalent:

- An account password authenticates through JSON-RPC, including on Odoo 19.
- An API key is required as the bearer credential for Odoo 19 JSON-2.
- Password rotation does not rotate or revoke an API key, and API-key rotation does not change the login password.

The initial API key cannot be generated through JSON-RPC or JSON-2. Odoo protects the interactive API-key wizard with an identity check and rejects remote calls to the private `_generate()` method. Create the initial key through the Odoo UI or a controlled server-side `odoo shell`, and write the returned value directly to a secrets manager without logging it.

For Odoo 18 and later, `_generate()` requires an expiration date. Odoo 19 additionally limits the expiration to the largest `api_key_duration` configured on the user's groups, defaulting to one day when every value is zero. A reviewed, root-only bootstrap may use `with_user(service_user).sudo()._generate(...)`: `with_user()` binds the key to the service account, while `sudo()` permits the approved longer lifetime. Do not expose this privileged path through an application API.

After storing the key, validate the service-account identity and require Vodoo to report `transport: json-2`. Preserve a separate random account password only when interactive login or recovery is required.

## Modular Permission Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Service Account                          │
├─────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────┐  │
│  │           API Base (required for all)                 │  │
│  │  res.company, res.users, res.partner, mail.*          │  │
│  └───────────────────────────────────────────────────────┘  │
│                              │                              │
│     ┌────────────┬───────────┼───────────┬────────────┐    │
│     ▼            ▼           ▼           ▼            ▼    │
│  ┌──────┐   ┌─────────┐  ┌───────┐  ┌─────────┐  ┌─────┐  │
│  │ CRM  │   │ Project │  │ Know- │  │Helpdesk │  │ ... │  │
│  │      │   │         │  │ ledge │  │         │  │     │  │
│  └──────┘   └─────────┘  └───────┘  └─────────┘  └─────┘  │
└─────────────────────────────────────────────────────────────┘
```

**Principle:** Assign only the groups needed for your workflow.

### Example Configurations

```bash
# Full access bot (all modules) - recommended for most use cases
vodoo security create-user "Bot" bot@company.com --assign-groups

# Create user first, then assign all groups separately
vodoo security create-user "Bot" bot@company.com
vodoo security assign-bot --login bot@company.com

# Create user without any groups (for manual group assignment via Odoo UI)
vodoo security create-user "Bot" bot@company.com
```

## Admin Credentials Safety

Use admin credentials only when bootstrapping. Pass them inline to avoid storing in `.env`:

```bash
ODOO_USERNAME=admin@example.com \
ODOO_PASSWORD=... \
vodoo security create-user "Bot" bot@company.com --assign-groups
```

Once setup is complete, switch to the service account for day-to-day operations.

## Key Security Properties

| Property | Value | Why |
|----------|-------|-----|
| `share` | `True` | Not billed as internal user |
| `base.group_user` | Removed | No web UI access |
| `base.group_portal` | Removed | No portal field restrictions |
| Groups | Custom API groups only | Least privilege |

## Important Limitations

### Project Visibility

The bot must be a **follower** of projects to access them.

**In Odoo UI:** Open each project → Followers → Add the bot user.

### Knowledge Articles

- ✅ Read/write existing articles
- ✅ Create child articles (under existing parent)
- ❌ Create root workspace articles (requires internal user)
- ❌ Delete articles (requires Administrator)

### Comments vs Notes

| Type | Subtype | Non-internal users |
|------|---------|-------------------|
| Comments | Discussions (`internal=False`) | ✅ Allowed |
| Internal Notes | Note (`internal=True`) | ✅ Allowed (via `message_type=notification`) |

Vodoo handles this automatically when using `comment` and `note` commands.

### mail.message Creation Requirements

Creating messages directly via the Odoo API requires:

1. **Access rights**: User must be in a group with `mail.message` create permission (API Base provides this)
2. **Document access**: User must have access to the related document (e.g., be a follower for projects)
3. **Subtype**: The `subtype_id` field must be provided. Vodoo resolves the stable XML IDs `mail.mt_comment` and `mail.mt_note` rather than translated subtype names.

Without `subtype_id`, Odoo's security checks will reject the create operation. The API Base group therefore includes read-only access to `ir.model.data` for XML-ID resolution.

### Requested Author Attribution (`author_id`)

Cross-user author attribution requires an internal authenticated user. Odoo may reject or override a different `author_id` for share users, which can reliably attribute messages only to their own partner.

| User Type | Can create messages | Cross-user author attribution |
|-----------|--------------------|-------------------------------|
| Share user | ✅ (with subtype_id) | ❌ May be rejected or forced to own partner |
| Internal user | ✅ | ✅ |

**To enable cross-user author attribution**, the bot must be an internal user:

```bash
# Add bot to base.group_user (makes it internal)
vodoo model call res.users write --args='[[USER_ID], {"group_ids": [[4, 1]]}]'

# Verify (share should be False)
vodoo model read res.users USER_ID --field share
```

**Trade-off:** Internal users count as paid seats on Odoo.com.

**To revert to share user:**

```bash
# Remove base.group_user
vodoo model call res.users write --args='[[USER_ID], {"group_ids": [[3, 1]]}]'
```

### User Creation

Creating users requires the **Access Rights** group (admin only). Service accounts cannot create other users.

## Credential Rotation

Odoo has **no built-in password expiration**. Implement manual rotation:

1. Generate new password for the bot
2. Update `.env` or secrets manager
3. Test authentication

```bash
# Generate and set new password (as admin)
ODOO_USERNAME=admin@example.com ODOO_PASSWORD=... \
vodoo security set-password --login bot@company.com

# Or set a specific password
ODOO_USERNAME=admin@example.com ODOO_PASSWORD=... \
vodoo security set-password --login bot@company.com --password NewSecurePassword123
```

## Disabling a Service Account

Immediately revoke all access:

```bash
ODOO_USERNAME=admin@example.com ODOO_PASSWORD=... \
vodoo model update res.users 42 active=false
```

This instantly disables password and API key authentication.

## Further Reading

- [Odoo Security Documentation](https://www.odoo.com/documentation/17.0/developer/reference/backend/security.html)
