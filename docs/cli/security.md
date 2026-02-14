# vodoo security

Manage Vodoo API security groups and service accounts. See the full [Security Guide](../development/security.md) for architecture details.

## Commands

### create-groups

Create all Vodoo API security groups (idempotent).

```bash
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

### create-user

Create a dedicated service account.

```bash
# Basic (generates password)
vodoo security create-user "Vodoo Bot" bot@company.com

# With specific password
vodoo security create-user "Vodoo Bot" bot@company.com --password MySecretPass123

# With all API groups assigned
vodoo security create-user "Vodoo Bot" bot@company.com --assign-groups
```

!!! note
    Requires admin credentials (Access Rights group).

### assign-bot

Assign all Vodoo API groups to an existing user.

```bash
# By login
vodoo security assign-bot --login bot@company.com

# By user ID
vodoo security assign-bot --user-id 42

# Keep existing default groups
vodoo security assign-bot --login bot@company.com --keep-default-groups
```

### set-password

Set or reset a user's password.

```bash
# Generate new password
vodoo security set-password --login bot@company.com

# Set specific password
vodoo security set-password --login bot@company.com --password NewPass123

# By user ID
vodoo security set-password --user-id 42
```
