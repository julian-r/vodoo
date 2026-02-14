# Quick Start

This guide walks you through your first Vodoo commands after [installation](installation.md) and [configuration](configuration.md).

## 1. Test Your Connection

```bash
# Read your own user record
vodoo model read res.users --domain='[["login","=","your@email.com"]]' --field name --field login
```

If this returns your user record, you're connected.

## 2. Browse Data

```bash
# List helpdesk tickets (enterprise)
vodoo helpdesk list

# List project tasks
vodoo project-task list

# List CRM leads
vodoo crm list

# List projects
vodoo project list

# List knowledge articles (enterprise)
vodoo knowledge list
```

## 3. Search and Filter

Every `list` command supports filters:

```bash
# Search across text fields
vodoo crm list --search "acme"

# Filter by stage
vodoo helpdesk list --stage "In Progress"

# Combine filters
vodoo project-task list --project "Website Redesign" --stage "In Progress" --limit 20
```

## 4. View Details

```bash
# Show full detail for a record
vodoo helpdesk show 42
vodoo crm show 15
```

## 5. Add Comments and Notes

```bash
# Internal note (not visible to customers)
vodoo helpdesk note 42 "Investigated — root cause is a config issue"

# Public comment (visible to customers)
vodoo helpdesk comment 42 "We've identified the issue and are working on a fix"
```

## 6. Manage Timers

```bash
# Start a timer on a task
vodoo timer start --task 42

# Check running timers
vodoo timer active

# Stop all timers
vodoo timer stop
```

## 7. Work with Attachments

```bash
# Upload a file
vodoo helpdesk attach 42 screenshot.png

# List attachments
vodoo helpdesk attachments 42

# Download an attachment by ID
vodoo helpdesk download 789
```

## 8. Use as a Python Library

```python
from vodoo import OdooClient, OdooConfig
from vodoo.crm import list_leads, add_note

config = OdooConfig(
    url="https://my.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)
client = OdooClient(config)

# List open opportunities
leads = list_leads(
    client,
    domain=[["type", "=", "opportunity"]],
    limit=10,
)
for lead in leads:
    print(f"{lead['id']}: {lead['name']}")

# Add a note
add_note(client, lead_id=42, message="Synced from external system")
```

## Next Steps

- :material-console: [CLI Reference](../cli/index.md) — full command documentation
- :material-language-python: [API Reference](../api/index.md) — library API docs
- :material-shield: [Security Guide](../development/security.md) — service account setup
- :material-robot: [AI Assistants](../guide/ai-assistants.md) — using with Claude Code
