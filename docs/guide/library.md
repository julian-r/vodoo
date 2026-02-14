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

## Domain Namespaces

Each domain module provides a namespace on the client with high-level methods:

### Helpdesk
```python
# List tickets
tickets = client.helpdesk.list(domain=[["stage_id.name", "=", "In Progress"]], limit=10)
# Get a single ticket with all fields
ticket = client.helpdesk.get(42)
# Add a comment (visible to customer)
client.helpdesk.comment(42, message="We're looking into this")
# Add an internal note
client.helpdesk.note(42, message="Root cause: config mismatch")
# Upload an attachment
attachment_id = client.helpdesk.attach(42, file_path="logs.txt")
```

### CRM

```python
# List opportunities
opps = client.crm.list(
    domain=[["type", "=", "opportunity"]],
    limit=20,
)
# Update fields
client.crm.set(15, values={"expected_revenue": 50000})
```

### Project Tasks

```python
tasks = client.tasks.list(domain=[["project_id.name", "=", "Website"]], limit=10)
task = client.tasks.get(7)
client.tasks.comment(7, message="Deployed to staging")
```

### Timers

```python
# Start a timer on a task
client.timer.start_task(42)
# Get today's timesheets
timesheets = client.timer.today()
# Stop all running timers
client.timer.stop()
```

## Transport Layer

Vodoo auto-detects the Odoo version and selects the right transport:

```python
# Check which transport is in use
print(client.is_json2)  # True for Odoo 19+, False for 17-18

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
Vodoo provides a full async API under `vodoo.aio` using [httpx](https://www.python-httpx.org/) for non-blocking HTTP. The `AsyncOdooClient` has the same namespace properties, but methods return awaitables.
```python
import asyncio
from vodoo import AsyncOdooClient, OdooConfig
    url="https://my.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)
async def main():
    async with AsyncOdooClient(config) as client:
        # Same API, just awaited
        tickets = await client.helpdesk.list(limit=5)
        # Concurrent requests with asyncio.gather
        tickets, leads = await asyncio.gather(
            client.helpdesk.list(limit=10),
            client.crm.list(limit=10),
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
tickets: list[dict[str, Any]] = client.helpdesk.list(limit=5)
ticket_id: int = client.create("helpdesk.ticket", {"name": "New ticket"})
success: bool = client.write("helpdesk.ticket", [ticket_id], {"priority": "2"})
```
