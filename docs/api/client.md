# OdooClient

The main entry point for interacting with Odoo. Domain operations are available as namespace properties on the client instance.

## Domain Namespaces

| Property | Class | Description |
|----------|-------|-------------|
| `client.helpdesk` | `HelpdeskNamespace` | Helpdesk ticket operations |
| `client.crm` | `CRMNamespace` | CRM lead/opportunity operations |
| `client.tasks` | `TaskNamespace` | Project task operations |
| `client.projects` | `ProjectNamespace` | Project operations |
| `client.knowledge` | `KnowledgeNamespace` | Knowledge article operations |
| `client.timer` | `TimerNamespace` | Timer and timesheet management |
| `client.security` | `SecurityNamespace` | Security group management |
| `client.generic` | `GenericNamespace` | Generic model operations |

```python
from vodoo import OdooClient, OdooConfig

config = OdooConfig(url="https://my.odoo.com", database="mydb",
                    username="bot@example.com", password="api-key")

with OdooClient(config) as client:
    tickets = client.helpdesk.list(limit=10)
    client.helpdesk.comment(42, "fixed")

    leads = client.crm.list(limit=5)
    tasks = client.tasks.list(limit=5)
```

::: vodoo.client.OdooClient
    options:
      show_source: true
      members_order: source
