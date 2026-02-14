# Async API

Vodoo provides a full async API under `vodoo.aio`. Every sync module has an async counterpart with the same function signatures, but using `async`/`await`.

The async transport uses [httpx](https://www.python-httpx.org/) for non-blocking HTTP.

## Quick Start

```python
import asyncio
from vodoo import AsyncOdooClient, OdooConfig

config = OdooConfig(
    url="https://my.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)

async def main():
    async with AsyncOdooClient(config) as client:
        partners = await client.search_read(
            "res.partner",
            domain=[["is_company", "=", True]],
            fields=["name", "email"],
            limit=10,
        )
        for p in partners:
            print(p["name"])

asyncio.run(main())
```

## Domain Helpers

Each sync domain module has an async equivalent:

| Sync | Async |
|------|-------|
| `vodoo.helpdesk` | `vodoo.aio.helpdesk` |
| `vodoo.project` | `vodoo.aio.project` |
| `vodoo.project_project` | `vodoo.aio.project_project` |
| `vodoo.crm` | `vodoo.aio.crm` |
| `vodoo.knowledge` | `vodoo.aio.knowledge` |
| `vodoo.timer` | `vodoo.aio.timer` |
| `vodoo.generic` | `vodoo.aio.generic` |
| `vodoo.security` | `vodoo.aio.security` |
| `vodoo.base` | `vodoo.aio.base` |
| `vodoo.auth` | `vodoo.aio.auth` |

```python
from vodoo.aio.helpdesk import list_tickets, add_note
from vodoo.aio.crm import list_leads

async with AsyncOdooClient(config) as client:
    tickets = await list_tickets(client, limit=5)
    leads = await list_leads(client, domain=[["type", "=", "opportunity"]])
    await add_note(client, ticket_id=42, message="Checked via async API")
```

## Concurrent Requests

The async API shines when you need to make multiple independent calls:

```python
import asyncio
from vodoo.aio.helpdesk import list_tickets
from vodoo.aio.crm import list_leads
from vodoo.aio.project import list_tasks

async with AsyncOdooClient(config) as client:
    # Run all three queries concurrently
    tickets, leads, tasks = await asyncio.gather(
        list_tickets(client, limit=10),
        list_leads(client, limit=10),
        list_tasks(client, limit=10),
    )
```

## Reference

### AsyncOdooClient

::: vodoo.aio.client.AsyncOdooClient
    options:
      show_source: true
      members_order: source

### AsyncOdooTransport

::: vodoo.aio.transport
    options:
      show_source: true
      members_order: source
      members:
        - AsyncOdooTransport
        - AsyncLegacyTransport
        - AsyncJSON2Transport
