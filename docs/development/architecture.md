# Architecture

## Overview

Vodoo follows a layered architecture where domain modules delegate shared operations to a base layer, and the transport layer handles protocol differences between Odoo versions. The entire stack is available in both sync and async variants.

```
┌──────────────────────────────────────────────────────┐
│                    CLI (main.py)                     │
│              Typer subcommands + Rich UI             │
├──────────────────────────────────────────────────────┤
│              Domain Modules                          │
│  helpdesk │ project │ crm │ knowledge │ timer │ ...  │
│           (sync in vodoo.*, async in vodoo.aio.*)    │
├──────────────────────────────────────────────────────┤
│              Base Layer                              │
│  base.py / aio/base.py — CRUD, messaging, display   │
├──────────────────────────────────────────────────────┤
│              Client                                  │
│  OdooClient (sync) │ AsyncOdooClient (async)         │
├──────────────────────────────────────────────────────┤
│              Transport                               │
│  Sync: LegacyTransport / JSON2Transport (httpx)      │
│  Async: AsyncLegacyTransport / AsyncJSON2Transport   │
│         (httpx)                                      │
├──────────────────────────────────────────────────────┤
│              Exceptions (exceptions.py)              │
│  VodooError → TransportError → OdooUserError → ...   │
└──────────────────────────────────────────────────────┘
```

## Design Patterns

### Domain Delegation

Each domain module defines a `MODEL` constant and thin wrappers around `base.py` functions:

```python
# helpdesk.py (sync) / aio/helpdesk.py (async)
MODEL = "helpdesk.ticket"
TAG_MODEL = "helpdesk.tag"

def add_comment(client, ticket_id, message, ...):
    return base_add_comment(client, MODEL, ticket_id, message, ...)
```

This keeps domain modules focused on model-specific concerns (field names, default fields) while all shared logic lives in `base.py`.

### Sync / Async Parity

Every sync module under `vodoo.*` has an async mirror under `vodoo.aio.*` with identical function signatures (but `async def` / `await`). The two stacks share:

- `config.py` — configuration (no I/O)
- `exceptions.py` — exception hierarchy
- `timer.py` data classes (`Timesheet`, `TimerBackend` etc.)

### Transport Abstraction

The `OdooTransport` ABC defines the interface. Four implementations exist:

| Transport | Odoo Versions | Protocol | HTTP Library |
|-----------|---------------|----------|--------------|
| `LegacyTransport` | 17–18 | `POST /jsonrpc` | `httpx` |
| `JSON2Transport` | 19+ | `POST /json/2/<model>/<method>` | `httpx` |
| `AsyncLegacyTransport` | 17–18 | `POST /jsonrpc` | `httpx` |
| `AsyncJSON2Transport` | 19+ | `POST /json/2/<model>/<method>` | `httpx` |

Auto-detection happens on client init: it tries JSON-2 first, falls back to legacy.

### Exception Mapping

The transport layer inspects `data.name` in JSON-RPC error responses and maps Odoo server exceptions to typed Python exceptions:

```
odoo.exceptions.AccessError    → OdooAccessError
odoo.exceptions.AccessDenied   → OdooAccessDeniedError
odoo.exceptions.UserError      → OdooUserError
odoo.exceptions.ValidationError → OdooValidationError
odoo.exceptions.MissingError   → OdooMissingError
```

This is handled by `transport_error_from_data()` using `ODOO_EXCEPTION_MAP` in `exceptions.py`.

### Configuration

`OdooConfig` uses Pydantic Settings to merge values from:

1. Environment variables (`ODOO_URL`, etc.)
2. `.env` files (searched in priority order)
3. Direct constructor arguments

### Versioning

The version is derived from git tags via `hatch-vcs` — no hardcoded version string. `__init__.py` reads it at runtime via `importlib.metadata.version("vodoo")`.

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `main.py` | CLI commands via Typer, output formatting |
| `client.py` | Sync client, transport auto-detection |
| `aio/client.py` | Async client, lazy transport init, context manager |
| `transport.py` | Sync HTTP (`httpx`) |
| `aio/transport.py` | Async HTTP (`httpx`) |
| `config.py` | Configuration loading and validation |
| `exceptions.py` | Exception hierarchy + Odoo error mapping |
| `auth.py` / `aio/auth.py` | Sudo operations, message posting as other users |
| `base.py` / `aio/base.py` | Shared CRUD, messaging, attachments, Rich display |
| `security.py` / `aio/security.py` | Security group creation, user management |

## Transport Protocol Details

### Legacy JSON-RPC (Odoo 17–18)

```
POST /jsonrpc
{
  "jsonrpc": "2.0",
  "method": "call",
  "params": {
    "service": "object",
    "method": "execute_kw",
    "args": [db, uid, password, model, method, args, kwargs]
  }
}
```

### JSON-2 (Odoo 19+)

```
POST /json/2/res.partner/search_read
Authorization: bearer <api-key>
X-Odoo-Database: <db>
{
  "domain": [["is_company", "=", true]],
  "fields": ["name", "email"],
  "limit": 10
}
```

JSON-2 is ~3-4× faster due to reduced envelope overhead and direct model routing.

## HTTP Dependencies

- **Sync** — uses [httpx](https://www.python-httpx.org/) for HTTP
- **Async** — uses [httpx](https://www.python-httpx.org/) for non-blocking HTTP
