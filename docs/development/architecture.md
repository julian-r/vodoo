# Architecture

## Overview

Vodoo follows a layered architecture where domain modules delegate shared operations to a base layer, and the transport layer handles protocol differences between Odoo versions. The entire stack is available in both sync and async variants.

```
│                    CLI (main.py)                     │
│              Typer subcommands + Rich UI             │
├──────────────────────────────────────────────────────┤
│              Domain Namespaces                        │
│  client.helpdesk │ .crm │ .tasks │ .projects │ ...   │
│     DomainNamespace subclasses (vodoo._domain)        │
│     AsyncDomainNamespace subclasses (vodoo.aio._domain)│
├──────────────────────────────────────────────────────┤
│              Base Layer                              │
│  _domain.py / aio/_domain.py — CRUD, messaging,     │
│  tags, attachments (shared via inheritance)           │
├──────────────────────────────────────────────────────┤
│              Client                                  │
│  OdooClient (sync) │ AsyncOdooClient (async)         │
├──────────────────────────────────────────────────────┤
│              Transport                               │
│  Sync: LegacyTransport / JSON2Transport (HTTPX2)     │
│  Async: AsyncLegacyTransport / AsyncJSON2Transport   │
│         (HTTPX2)                                     │
├──────────────────────────────────────────────────────┤
│              Exceptions (exceptions.py)              │
│  VodooError → TransportError → OdooUserError → ...   │
└──────────────────────────────────────────────────────┘
```

## Design Patterns

### Domain Namespaces

Each domain is exposed as a namespace attribute on the client. Namespaces are `DomainNamespace` subclasses that set class-level attributes (`_model`, `_default_fields`, etc.) and optionally add domain-specific methods:

```python
# vodoo/helpdesk.py
class HelpdeskNamespace(DomainNamespace):
    _model = "helpdesk.ticket"
    _tag_model = "helpdesk.tag"
    _default_fields = ["id", "name", "partner_id", "stage_id", ...]
    _record_type = "Ticket"

    def create(self, name: str, *, description=None, ...) -> int: ...
```

Namespaces are instantiated eagerly on client init via factory functions (to avoid circular imports):

```python
# vodoo/client.py
self.helpdesk = _make_helpdesk(self)  # HelpdeskNamespace(self)
self.crm = _make_crm(self)           # CrmNamespace(self)
self.tasks = _make_tasks(self)       # TaskNamespace(self)
# ... etc.
```

This keeps domain-specific concerns (field names, model constants) in thin subclasses while all shared logic (CRUD, messaging, tags, attachments) lives in `DomainNamespace`.

### Sync / Async Parity
Every sync namespace under `vodoo.*` has an async mirror under `vodoo.aio.*` — `DomainNamespace` / `AsyncDomainNamespace` with identical method signatures (but `async def` / `await`). The two stacks share:
- `config.py` — configuration (no I/O)
- `exceptions.py` — exception hierarchy
- `timer.py` data classes (`Timesheet`, `TimerBackend` etc.)
### Transport Abstraction

The `OdooTransport` ABC defines the interface. Four implementations exist:

| Transport | Odoo Versions | Protocol | HTTP Library |
|-----------|---------------|----------|--------------|
| `LegacyTransport` | 17–18 | `POST /jsonrpc` | `httpx2` |
| `JSON2Transport` | 19+ | `POST /json/2/<model>/<method>` | `httpx2` |
| `AsyncLegacyTransport` | 17–18 | `POST /jsonrpc` | `httpx2` |
| `AsyncJSON2Transport` | 19+ | `POST /json/2/<model>/<method>` | `httpx2` |

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
|--------|---------------|
| `main.py` | CLI commands via Typer, output formatting |
| `client.py` | Sync client, transport auto-detection, namespace wiring |
| `aio/client.py` | Async client, lazy transport init, context manager, namespace wiring |
| `transport.py` | Sync HTTP (`httpx2`) |
| `aio/transport.py` | Async HTTP (`httpx2`) |
| `config.py` | Configuration loading and validation |
| `exceptions.py` | Exception hierarchy + Odoo error mapping |
| `_domain.py` | `DomainNamespace` base class — shared CRUD, messaging, tags, attachments |
| `aio/_domain.py` | `AsyncDomainNamespace` base class — async mirror |
| `auth.py` / `aio/auth.py` | Authentication helpers and requested-author attribution for messages |
| `helpdesk.py` / `crm.py` / `account_moves.py` / ... | Domain namespace subclasses |
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

- **Sync** — uses [HTTPX2](https://pydantic.dev/docs/httpx2/) for HTTP
- **Async** — uses [HTTPX2](https://pydantic.dev/docs/httpx2/) for non-blocking HTTP

### HTTPX2 migration note

Vodoo uses `httpx2` directly and does not install or alias the original `httpx` package. Code that
interacts with a transport's underlying HTTP client, catches its HTTP exceptions, or supplies test
responses must therefore use `httpx2` types; original HTTPX and HTTPX2 objects are not
interchangeable.

HTTPX2 uses the operating system certificate store through `truststore` by default. Vodoo leaves
environment discovery enabled, so `SSL_CERT_FILE`, `SSL_CERT_DIR`, `HTTP_PROXY`, `HTTPS_PROXY`,
`ALL_PROXY`, and `NO_PROXY` continue to work. HTTP/2 is enabled and negotiated when the server or reverse
proxy supports it, with automatic HTTP/1.1 fallback. Legacy JSON-RPC requests now use HTTPX2's default
`python-httpx2/<version>` User-Agent; JSON-2 requests retain Vodoo's explicit `Vodoo` User-Agent.
