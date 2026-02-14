# Architecture

## Overview

Vodoo follows a layered architecture where domain modules delegate shared operations to a base layer, and the transport layer handles protocol differences between Odoo versions.

```
┌──────────────────────────────────────────────────────┐
│                    CLI (main.py)                     │
│              Typer subcommands + Rich UI             │
├──────────────────────────────────────────────────────┤
│              Domain Modules                          │
│  helpdesk.py │ project.py │ crm.py │ knowledge.py   │
│  project_project.py │ timer.py │ generic.py         │
├──────────────────────────────────────────────────────┤
│              Base Layer (base.py)                    │
│  Shared CRUD, messaging, attachments, display        │
├──────────────────────────────────────────────────────┤
│              Client (client.py)                      │
│  OdooClient — unified API, delegates to transport    │
├──────────────────────────────────────────────────────┤
│              Transport (transport.py)                │
│  LegacyTransport (JSON-RPC) │ JSON2Transport (REST) │
└──────────────────────────────────────────────────────┘
```

## Design Patterns

### Domain Delegation

Each domain module defines a `MODEL` constant and thin wrappers around `base.py` functions:

```python
# helpdesk.py
MODEL = "helpdesk.ticket"
TAG_MODEL = "helpdesk.tag"

def add_comment(client, ticket_id, message, ...):
    return base_add_comment(client, MODEL, ticket_id, message, ...)
```

This keeps domain modules focused on model-specific concerns (field names, default fields) while all shared logic lives in `base.py`.

### Transport Abstraction

The `OdooTransport` ABC defines the interface. Two implementations exist:

| Transport | Odoo Versions | Protocol | Auth |
|-----------|---------------|----------|------|
| `LegacyTransport` | 14–18 | `POST /jsonrpc` with service envelope | Session cookie |
| `JSON2Transport` | 19+ | `POST /json/2/<model>/<method>` | Bearer token |

Auto-detection happens in `OdooClient.__init__()`: it tries JSON-2 first, falls back to legacy.

### Configuration

`OdooConfig` uses Pydantic Settings to merge values from:

1. Environment variables (`ODOO_URL`, etc.)
2. `.env` files (searched in priority order)
3. Direct constructor arguments

## Module Responsibilities

| Module | Responsibility |
|--------|---------------|
| `main.py` | CLI commands via Typer, output formatting |
| `client.py` | Unified client API, transport auto-detection |
| `transport.py` | HTTP communication, JSON-RPC / JSON-2 protocol |
| `config.py` | Configuration loading and validation |
| `auth.py` | Sudo operations, message posting as other users |
| `base.py` | Shared CRUD, messaging, attachments, Rich display |
| `exceptions.py` | Exception hierarchy |
| `security.py` | Security group creation, user management |

## Transport Protocol Details

### Legacy JSON-RPC (Odoo 14–18)

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

## No External HTTP Dependencies

Vodoo uses only `urllib.request` from the Python standard library — no `requests`, `httpx`, or `aiohttp`. This keeps the dependency footprint minimal.
