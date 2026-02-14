# Using Vodoo as a Library

Vodoo is not just a CLI — it's a fully typed Python library you can import into your own projects.

## Installation

```bash
pip install vodoo
```

## Basic Usage

```python
from vodoo import OdooClient, OdooConfig

# Configure the connection
config = OdooConfig(
    url="https://my.odoo.com",
    database="production",
    username="bot@example.com",
    password="api-key-here",
)

# Create a client (auto-detects Odoo version and transport)
client = OdooClient(config)
```

## Low-Level Client Methods

The `OdooClient` exposes standard Odoo ORM methods:

```python
# Search for record IDs
ids = client.search("res.partner", domain=[["is_company", "=", True]], limit=10)

# Read specific records
records = client.read("res.partner", ids=ids, fields=["name", "email"])

# Search and read in one call
partners = client.search_read(
    "res.partner",
    domain=[["email", "ilike", "@acme.com"]],
    fields=["name", "email", "phone"],
    limit=20,
    order="name asc",
)

# Create a record
partner_id = client.create("res.partner", {"name": "Acme Corp", "is_company": True})

# Update a record
client.write("res.partner", [partner_id], {"phone": "+1-555-0123"})

# Delete a record
client.unlink("res.partner", [partner_id])

# Autocomplete search
results = client.name_search("res.partner", "Acme", limit=5)
# Returns: [(42, "Acme Corp"), (43, "Acme Inc")]
```

## Domain Helpers

Each domain module provides high-level functions:

### Helpdesk

```python
from vodoo.helpdesk import (
    list_tickets,
    get_ticket,
    add_comment,
    add_note,
    create_attachment,
    list_attachments,
)

# List tickets
tickets = list_tickets(client, domain=[["stage_id.name", "=", "In Progress"]], limit=10)

# Get a single ticket with all fields
ticket = get_ticket(client, ticket_id=42)

# Add a comment (visible to customer)
add_comment(client, ticket_id=42, message="We're looking into this")

# Add an internal note
add_note(client, ticket_id=42, message="Root cause: config mismatch")

# Upload an attachment
attachment_id = create_attachment(client, ticket_id=42, file_path="logs.txt")
```

### CRM

```python
from vodoo.crm import list_leads, add_note, set_lead_fields

# List opportunities
opps = list_leads(
    client,
    domain=[["type", "=", "opportunity"]],
    limit=20,
)

# Update fields
set_lead_fields(client, lead_id=15, values={"expected_revenue": 50000})
```

### Project Tasks

```python
from vodoo.project import list_tasks, get_task, add_comment

tasks = list_tasks(client, domain=[["project_id.name", "=", "Website"]], limit=10)
task = get_task(client, task_id=7)
add_comment(client, task_id=7, message="Deployed to staging")
```

### Timers

```python
from vodoo.timer import start_timer, stop_timers, get_today_timesheets

# Start a timer on a task
start_timer(client, task_id=42)

# Get today's timesheets
timesheets = get_today_timesheets(client)

# Stop all running timers
stop_timers(client)
```

## Transport Layer

Vodoo auto-detects the Odoo version and selects the right transport:

```python
# Check which transport is in use
print(client.is_json2)  # True for Odoo 19+, False for 14-18

# Access the underlying transport
transport = client.transport
print(type(transport))  # JSON2Transport or LegacyTransport
```

You can also force a specific transport:

```python
from vodoo.transport import LegacyTransport, JSON2Transport

# Force legacy JSON-RPC
transport = LegacyTransport(
    url="https://my.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)
client = OdooClient(config, transport=transport)
```

## Async API

Vodoo provides a full async API under `vodoo.aio` using [httpx](https://www.python-httpx.org/) for non-blocking HTTP. Every sync module has an async counterpart with identical function signatures.

```python
import asyncio
from vodoo import AsyncOdooClient, OdooConfig
from vodoo.aio.helpdesk import list_tickets
from vodoo.aio.crm import list_leads

config = OdooConfig(
    url="https://my.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)

async def main():
    async with AsyncOdooClient(config) as client:
        # Same API, just awaited
        tickets = await list_tickets(client, limit=5)

        # Concurrent requests with asyncio.gather
        tickets, leads = await asyncio.gather(
            list_tickets(client, limit=10),
            list_leads(client, limit=10),
        )

asyncio.run(main())
```

See the [Async API reference](../api/async.md) for all available modules.

## Error Handling

All Vodoo exceptions inherit from `VodooError`. The Odoo server-side exceptions (`OdooUserError` and subclasses) are automatically mapped from the server's error response, so you can handle specific failure modes:

```python
from vodoo import (
    VodooError,
    AuthenticationError,
    RecordNotFoundError,
    TransportError,
)
from vodoo.exceptions import (
    OdooAccessError,
    OdooAccessDeniedError,
    OdooValidationError,
    OdooMissingError,
)

try:
    client.write("res.partner", [42], {"email": "invalid"})
except OdooAccessError:
    print("You don't have permission for this operation")
except OdooValidationError as e:
    print(f"Constraint violated: {e}")
except OdooMissingError:
    print("Record no longer exists")
except RecordNotFoundError as e:
    print(f"Not found: {e.model} #{e.record_id}")
except AuthenticationError:
    print("Bad credentials")
except TransportError as e:
    print(f"RPC error [{e.code}]: {e}")
except VodooError as e:
    print(f"Vodoo error: {e}")
```

The full hierarchy:

```
VodooError
├── ConfigurationError
│   └── InsecureURLError
├── AuthenticationError
├── RecordNotFoundError
├── RecordOperationError
├── TransportError
│   └── OdooUserError              ← odoo.exceptions.UserError
│       ├── OdooAccessDeniedError  ← odoo.exceptions.AccessDenied
│       ├── OdooAccessError        ← odoo.exceptions.AccessError
│       ├── OdooMissingError       ← odoo.exceptions.MissingError
│       └── OdooValidationError    ← odoo.exceptions.ValidationError
└── FieldParsingError
```

See the [Exceptions API reference](../api/exceptions.md) for details.

## Type Safety

Vodoo is fully typed with strict mypy. All functions have type annotations, so your IDE will provide autocompletion and type checking out of the box.

```python
# Your IDE knows these types:
tickets: list[dict[str, Any]] = list_tickets(client, limit=5)
ticket_id: int = client.create("helpdesk.ticket", {"name": "New ticket"})
success: bool = client.write("helpdesk.ticket", [ticket_id], {"priority": "2"})
```
