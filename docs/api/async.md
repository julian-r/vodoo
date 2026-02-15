# Async API

Vodoo provides a full async API via `AsyncOdooClient`. It exposes the same domain namespaces as the sync client, but all methods are `async` and use [httpx](https://www.python-httpx.org/) for non-blocking HTTP.

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

## Domain Namespaces

The async client has the same namespace properties as the sync client. All namespace methods must be awaited:

```python
async with AsyncOdooClient(config) as client:
    tickets = await client.helpdesk.list(limit=5)
    leads = await client.crm.list(domain=[["type", "=", "opportunity"]])
    await client.helpdesk.note(ticket_id=42, message="Checked via async API")
```

## Concurrent Requests

The async API shines when you need to make multiple independent calls:

```python
import asyncio

async with AsyncOdooClient(config) as client:
    # Run all three queries concurrently
    tickets, leads, tasks = await asyncio.gather(
        client.helpdesk.list(limit=10),
        client.crm.list(limit=10),
        client.tasks.list(limit=10),
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
