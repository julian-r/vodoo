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

## Best-effort freshness checks

`client.write`, `client.generic.update`, and domain `.set` methods (also async)
accept the optional keyword `check_write_date`:

```python
from vodoo import StaleRevisionError

observed = client.tasks.get(42, fields=["write_date"])
try:
    client.tasks.set(42, {"name": "Reviewed"}, check_write_date=observed["write_date"])
except StaleRevisionError as error:
    print(error.expected, error.current)  # Mutation was not attempted.

# Generic and low-level equivalents:
client.generic.update("project.task", 42, {"name": "Reviewed"}, check_write_date="2026-10-03 13:00:20")
client.write("project.task", [42], {"name": "Reviewed"}, check_write_date="2026-10-03 13:00:20")
# Async: await client.tasks.set(..., check_write_date=expected)
```

CLI field-update commands expose the same check:

```bash
vodoo project-task set 42 --check-write-date '2026-10-03 13:00:20' name=Reviewed
vodoo --json model update project.task 42 --check-write-date '2026-10-03 13:00:20' name=Reviewed
```

Available on `project-task set`, `project set`, `helpdesk set`, `crm set`, and
`model update`. The timestamp must use the exact UTC `YYYY-MM-DD HH:MM:SS` format
returned by ordinary Odoo reads; fractional seconds, timezone suffixes, and
invalid dates are rejected, not silently normalized. For a low-level bulk write,
every requested record must match the same supplied timestamp before any write
is attempted. Without this option, existing unguarded behavior is unchanged.

!!! warning "Non-atomic preflight, not compare-and-set"
    Values are prepared first, then Vodoo reads the current revision and immediately
    attempts an ordinary write if it matches. **Another writer can commit between
    that read and write.** Odoo serializes ordinary datetime values to whole seconds,
    so **same-second changes can go undetected**. Appending zeros cannot recover
    missing fractional precision. Successful mutation is not proof that no change
    intervened; audit timestamps are not unique monotonic revision tokens.

    Odoo can retry a failed ordinary write transaction server-side without repeating
    the client's preflight. The client does not automatically resend writes after
    transport failure, but the mutation outcome may already be unknown. A post-write
    read cannot prove absence of a lost update or safely undo one. True atomic
    protection requires a separately provisioned server capability.

A stale observation raises `StaleRevisionError` (model, record ID, expected/current
revision); CLI exit **3** and JSON `type`/`code` **`stale_preflight_conflict`** distinguish
it from other failures. JSON also includes `expected`, `current`, `model`, `id`,
`mutation_attempted: false`, and `best_effort: true`. Malformed expected timestamps
raise `RevisionInputError` (CLI exit 2 / `invalid_revision`). Missing records raise
`RecordNotFoundError` (exit 1 / `not_found`); absent, false, or malformed observed
revisions raise `UnverifiableRevisionError` (exit 1 / `unverifiable_revision`).
All prevent a mutation attempt. Read permission errors and server errors (including
models rejecting a `write_date` read) remain their original errors, not conflicts
or proof of deletion. No check failure falls back to an unguarded write, refreshes
the expected timestamp, or retries a mutation.

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
# Composite read-only context; inspect complete/errors/pagination before acting.
context = client.tasks.context(7)
client.tasks.comment(7, message="Deployed to staging")

# All fields are sent in one create request, never a placeholder plus updates.
task_id = client.tasks.create(
    "Task title",
    project_id=2,
    description="**Details**",  # Markdown by default; use HTML(...) for raw HTML
    stage_id=15,
    tag_ids=[2, 5],
    user_ids=[5, 6],
    parent_id=100,
    depend_on_ids=[90, 91],
)
```

The async namespace accepts the same arguments: `await client.tasks.create(...)`.
All relation IDs must be positive integers and are validated before creation.
`user_ids`, `tag_ids`, and `depend_on_ids` are ordinary ID lists; Vodoo converts them
to Odoo relation commands. Omitted relations retain Odoo defaults; an explicit empty
list requests an empty relation. The server validates record existence and access
rights as part of the single create operation.

The CLI accepts a positional title or `--name`/`--title` (not both), repeated
`--assignee`/`--user`, `--tag`, and `--depends-on` flags, plus `--stage` and `--parent`.
`--project` is required. `--description`/`--desc` accepts Markdown by default;
`--no-markdown` sends raw HTML instead. JSON output includes the created ID and
requested field values, including the description as supplied, without a follow-up read.

### Timers

```python
# Start a timer on a task
client.timer.start_task(42)
# Get today's timesheets
timesheets = client.timer.today()
# Stop all running timers
client.timer.stop()
```

## Record URLs

Domain namespaces build links to record form views without making an additional request:

```python
project = client.create("project.project", {"name": "Launch"})
print(client.projects.url(project))
# Odoo 19: https://my.odoo.com/odoo/project.project/42
# Odoo 17–18: https://my.odoo.com/web#id=42&model=project.project&view_type=form
```

After JSON-2 is explicitly selected or detected, `url()` uses Odoo 19's canonical path format. Legacy JSON-RPC retains the hash format. An async auto-detecting client used before any awaited operation also returns the legacy URL because URL generation remains synchronous and never performs a network request. Knowledge articles use their server-provided `article_url` when available and this transport-aware URL as a fallback.

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
Vodoo provides a full async API under `vodoo.aio` using [HTTPX2](https://pydantic.dev/docs/httpx2/) for non-blocking HTTP. The `AsyncOdooClient` has the same namespace properties, but methods return awaitables.
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
