<p align="center">
  <img src="docs/assets/logo.png" alt="Vodoo" width="200">
</p>

# Vodoo

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/vodoo)](https://pypi.org/project/vodoo/)
[![Documentation](https://img.shields.io/badge/docs-julian--r.github.io%2Fvodoo-blue)](https://julian-r.github.io/vodoo)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

A multi-language Odoo SDK for Python, TypeScript/Cloudflare Workers, and Swift, plus a Python CLI. Use it in scripts, services, apps, and automations — or as a CLI for quick ad-hoc operations and AI-assisted workflows.

Supports helpdesk tickets, project tasks, projects, CRM leads/opportunities, accounting moves, knowledge articles, and timesheets across Odoo 17–19.

**📖 [Full Documentation](https://julian-r.github.io/vodoo)** — Getting started, CLI reference, Python library guide, and API docs.

## Quick Start — Library

```python
from vodoo import OdooClient, OdooConfig, RecordNotFoundError

config = OdooConfig(
    url="https://my-instance.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key-or-password",
)
client = OdooClient(config)

# Namespace helpers on the client
tasks = client.tasks.list(limit=10)

# Generic client for any model
partners = client.search_read("res.partner", fields=["name", "email"], limit=5)

# Structured exceptions — catch what you need
try:
    record = client.generic.search("res.partner", [("id", "=", 999999999)])
except RecordNotFoundError as e:
    print(f"{e.model} #{e.record_id} not found")
```

## Quick Start — TypeScript

```bash
npm install vodoo
```

```typescript
import { OdooClient } from "vodoo";

const client = new OdooClient({
  url: "https://my-instance.odoo.com",
  database: "mydb",
  username: "bot@example.com",
  password: "api-key-or-password",
});
const tasks = await client.tasks.list({ limit: 10 });
```

The TypeScript package is Web Standards-only and is smoke-tested in Cloudflare workerd.

## Quick Start — Swift

Add this repository as a Swift Package dependency, then:

```swift
import Vodoo

let config = OdooConfig(
    url: URL(string: "https://my-instance.odoo.com")!,
    database: "mydb",
    username: "bot@example.com",
    password: "api-key-or-password"
)
let client = OdooClient(config: config)
let tasks = try await client.tasks.list(limit: 10)
let taskID = try await client.tasks.create(
    "Deploy",
    projectID: 7,
    options: CreateTaskOptions(description: "**Ship it**")
)
```

Python, TypeScript, and Swift provide the same non-CLI feature surface: generic CRUD,
projects and tasks, CRM pipelines, activities, account moves, helpdesk, knowledge,
documents, messaging, tags, attachments, security provisioning, and timers. Binary
and download APIs use native in-memory types for each runtime (`bytes`, `Uint8Array`,
and `Data`).

## Quick Start — CLI

```bash
# Run without installing
uvx vodoo crm list --search "acme"

# Or install globally
pip install vodoo
vodoo helpdesk list --stage "In Progress"
vodoo project-task show 42
vodoo timer start 42
```

Works well with AI assistants like Claude Code — natural language in, structured Odoo operations out.

## Odoo Version Support

| Version | Protocol | Status |
|---------|----------|--------|
| Odoo 17 | Legacy JSON-RPC | ✅ Fully tested |
| Odoo 18 | Legacy JSON-RPC | ✅ Fully tested |
| Odoo 19 | JSON-2 (bearer auth) | ✅ Fully tested |

Auto-detects the Odoo version and selects the appropriate transport. Odoo 19's JSON-2 API is ~3–4x faster than legacy JSON-RPC.

## Features

### Library

- 🐍 Clean Python API — `OdooClient` with namespace helpers (`client.helpdesk`, `client.crm`, etc.)
- ⚡ Full async support via `vodoo.aio` — `AsyncOdooClient` with async context manager
- 🌐 Feature-equivalent TypeScript SDK for Node.js and Cloudflare Workers
- 🍎 Feature-equivalent native Swift SDK distributed with Swift Package Manager
- 🎯 Structured exception hierarchy mirroring Odoo server errors
- 📦 No CLI dependencies loaded when imported as a library
- 🔒 Strict mypy typing throughout

### CLI

- 📋 Helpdesk tickets, project tasks, projects, CRM leads, knowledge articles
- ⏱️ Timer / timesheet management (start, stop, status)
- 💬 Comments, internal notes, tags, attachments
- 🔍 Search across text fields (name, email, phone, description)
- 🧰 Generic CRUD for any Odoo model
- 🎨 Rich terminal output with tables

### Shared

- 🔀 Auto-detecting transport layer (JSON-2 for Odoo 19+, legacy JSON-RPC for 17–18)
- ⚙️ Configuration via environment variables, `.env`, or `OdooConfig`
- 🔐 HTTPS enforcement warnings for production safety

## Installation

```bash
# From PyPI
pip install vodoo

# Or run the CLI without installing
uvx vodoo helpdesk list

# From source (development)
git clone https://github.com/julian-r/vodoo.git
cd vodoo
uv sync --all-extras
```

## Configuration

Create a `.vodoo.env`, `~/.config/vodoo/config.env`, or `.env` file:

```bash
ODOO_URL=https://your-odoo-instance.com
ODOO_DATABASE=your_database
ODOO_USERNAME=your_username
ODOO_PASSWORD=your_password_or_api_key
# Optional alternative: ODOO_PASSWORD_REF=op://Vault/Item/password
ODOO_DEFAULT_USER_ID=123  # Optional: default user for sudo operations
```

Multi-instance profiles are also supported:

- `.vodoo/instances/<instance>.env`
- `~/.config/vodoo/instances/<instance>.env`
- select via `vodoo --instance <instance> ...` or `VODOO_INSTANCE=<instance>`

Or set environment variables directly, or pass values to `OdooConfig()` in code.

Useful config helpers:

```bash
vodoo config list-instances
vodoo config show
vodoo config use staging
vodoo config test --instance staging
```

## Exception Hierarchy

All exceptions inherit from `VodooError` so you can catch broadly or narrowly:

```
VodooError
├── ConfigurationError
├── AuthenticationError
├── RecordNotFoundError          ← .model, .record_id attributes
├── RecordOperationError
├── TransportError               ← .code, .data attributes
│   └── OdooUserError            ← odoo.exceptions.UserError
│       ├── OdooAccessDeniedError
│       ├── OdooAccessError
│       ├── OdooMissingError
│       └── OdooValidationError
└── FieldParsingError
```

Server-side Odoo errors are automatically mapped to the matching exception class, so you can handle `OdooAccessError` separately from `OdooValidationError` without parsing error strings.

## Library Usage

### Namespace Helpers

Each Odoo domain is a namespace on the client with high-level methods:
from vodoo import OdooClient, OdooConfig
client = OdooClient(OdooConfig(
    url="https://odoo.example.com",
    database="prod",
    username="bot@example.com",
    password="api-key",
))
# Project tasks
tasks = client.tasks.list(domain=[("stage_id.name", "=", "In Progress")], limit=20)
task = client.tasks.get(42)
client.tasks.comment(42, "Deployed to staging")
leads = client.crm.list(domain=[("type", "=", "opportunity")], limit=20)
client.crm.set(123, {"expected_revenue": 50000, "probability": 75})
tickets = client.helpdesk.list(domain=[("stage_id.name", "=", "New")], limit=10)
client.timer.start_task(task_id=42)
client.timer.stop()
records = client.search_read("res.partner", [("is_company", "=", True)], fields=["name"])
new_id = client.create("res.partner", {"name": "Acme Corp", "is_company": True})
client.write("res.partner", [new_id], {"phone": "+1234567890"})
```

### Error Handling

```python
from vodoo import (
    OdooClient, OdooConfig, VodooError,
    AuthenticationError, RecordNotFoundError,
    OdooAccessError, OdooValidationError,
)

try:
    client = OdooClient(OdooConfig(...))
    client.write("res.partner", [999], {"name": "Updated"})
except AuthenticationError:
    print("Bad credentials")
except RecordNotFoundError as e:
    print(f"{e.model} #{e.record_id} does not exist")
except OdooAccessError:
    print("Insufficient permissions")
except OdooValidationError:
    print("Data constraint violated")
except VodooError as e:
    print(f"Something else went wrong: {e}")
```

## Async Usage

All library functionality is also available as async via `vodoo.aio`:

```python
from vodoo import OdooConfig
from vodoo.aio import AsyncOdooClient

config = OdooConfig(
    url="https://my-instance.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)

async with AsyncOdooClient(config) as client:
    # Namespace helpers
    tasks = await client.tasks.list(limit=10)
    partners = await client.search_read("res.partner", fields=["name", "email"], limit=5)
    # Comments / notes
    await client.crm.comment(123, "Async update")
```

Every sync namespace has an async counterpart — same methods, just `await`ed.

## CLI Usage

### CRM Leads/Opportunities

```bash
vodoo crm list --search "acme" --type opportunity --stage "Qualified"
vodoo crm show 123
vodoo crm set 123 expected_revenue=50000 probability=75
vodoo crm note 123 "Followed up via phone"
vodoo crm attach 123 proposal.pdf
vodoo crm url 123
```

### Project Tasks

```bash
vodoo project-task list --stage "In Progress"
vodoo project-task show 42
vodoo project-task comment 42 "Deployed to staging"
vodoo project-task attach 42 screenshot.png
```

### Accounting Moves

```bash
vodoo account-move list --company "Rath Technologie" --year 2025 --state posted
vodoo account-move attachments 3552
vodoo account-move download-all 3552 --output "~/Belege 2025" --extension pdf
```

### Projects

```bash
vodoo project list
vodoo project show 1
vodoo project note 1 "Sprint planning notes"
```

### Helpdesk Tickets (Enterprise)

```bash
vodoo helpdesk list --stage "New" --assigned-to "John"
vodoo helpdesk show 123
vodoo helpdesk note 123 "Internal update"
vodoo helpdesk comment 123 "We're looking into this"
vodoo helpdesk download 456 --output ./attachments/
```

### Knowledge Articles (Enterprise)

```bash
vodoo knowledge list --category workspace
vodoo knowledge create "Team Handbook" --body "# Onboarding\n\nWelcome!" --category workspace
vodoo knowledge show 123
vodoo knowledge note 123 "Updated installation section"
```

### Timers / Timesheets

```bash
vodoo timer start 42
vodoo timer status
vodoo timer stop
```

### Generic Model Operations

```bash
vodoo model read res.partner --domain='[["is_company","=",true]]' --field name --field email
vodoo model create res.partner name="Acme" email=info@acme.com
vodoo model update res.partner 123 phone="+123456789"
vodoo model delete res.partner 123
vodoo model call res.partner name_search --args='["Acme"]'
```

### Security / Service Accounts

```bash
vodoo security create-groups
vodoo security assign-bot --login service-vodoo@company.com
```

For production use, run Vodoo with a dedicated least-privilege service account. See the [Security Guide](https://julian-r.github.io/vodoo/development/security/).

## Documentation

Full docs at **[julian-r.github.io/vodoo](https://julian-r.github.io/vodoo)**:

- [Getting Started](https://julian-r.github.io/vodoo/getting-started/installation/) — Installation, configuration, quick start
- [CLI Reference](https://julian-r.github.io/vodoo/cli/) — All commands with examples
- [Library Guide](https://julian-r.github.io/vodoo/guide/library/) — Using Vodoo as a Python library
- [API Reference](https://julian-r.github.io/vodoo/api/) — Auto-generated from docstrings
- [Security Guide](https://julian-r.github.io/vodoo/development/security/) — Service account setup

## Project Structure

```
src/vodoo/
├── __init__.py           # Public API: OdooClient, OdooConfig, exceptions
├── exceptions.py         # Exception hierarchy (VodooError and subclasses)
├── client.py             # OdooClient — delegates to transport layer
├── transport.py          # Transport abstraction (JSON-2 + legacy JSON-RPC)
├── config.py             # Pydantic configuration from env/.env files
├── auth.py               # Authentication and sudo utilities
├── _domain.py            # DomainNamespace base — shared CRUD, messaging, attachments
├── main.py               # CLI entry point (Typer) — not loaded by library imports
├── helpdesk.py           # Helpdesk ticket operations (enterprise)
├── project_tasks.py      # Project task operations
├── projects.py           # Project operations
├── crm.py                # CRM lead/opportunity operations
├── account_moves.py      # Accounting move operations
├── knowledge.py          # Knowledge article operations (enterprise)
├── generic.py            # Generic model CRUD
├── security.py           # Security groups, user management
├── timer.py              # Timer/timesheet start, stop, status
└── aio/                  # Async versions of all modules above
    ├── client.py         # AsyncOdooClient
    ├── _domain.py        # AsyncDomainNamespace base
    ├── transport.py      # Async JSON-2 + legacy transports
    └── ...               # Async domain modules (same API, awaitable)
```

## Integration Tests

CI runs the Python, TypeScript, and Swift native SDK suites against real Community and Enterprise instances for every supported Odoo version. The local runner provisions the instance and runs Python and TypeScript:

```bash
./tests/integration/run.sh  # All Community editions (17, 18, 19)
./tests/integration/run.sh 19

# Enterprise requires a valid Odoo download code in the ignored .odoo-license file.
uv run python tests/integration/fetch_enterprise.py fetch 19
ENTERPRISE_BUILD_ONLY=1 ./tests/integration/run.sh 19
ENTERPRISE=1 ./tests/integration/run.sh 19
```

Enterprise archives and images remain local and contain licensed proprietary source; Docker's local build cache may retain their layers. See [Integration Tests](docs/development/integration-tests.md#enterprise-addons) for credential storage, secure downloads, provenance validation, CI behavior, and cleanup.

## Development

```bash
uv sync --all-extras
uv run ruff check .
uv run ruff format .
uv run mypy src/vodoo
pnpm --dir packages/typescript typecheck
pnpm --dir packages/typescript test

# Shared Python/TypeScript/Swift transport and codec contract
uv run pytest tests/conformance -q
swift test --enable-code-coverage
python3 scripts/check_swift_coverage.py "$(swift test --show-codecov-path)"
```

The Swift gate excludes generated sources and currently enforces 80% lines, 74% functions,
and 68% regions.

All three SDKs independently validate `conformance/fixtures/v1.json`; no language implementation is used as the conformance oracle. The fixture's protocol, date, binary, command, and operation rows are neutral cross-runtime vectors.

## Publishing

Version is derived from git tags via `hatch-vcs`:

```bash
git tag vX.Y.Z && git push origin vX.Y.Z
```

One release tag versions PyPI, npm, and the Swift Package. GitHub Actions publishes Python and TypeScript artifacts; Swift Package Manager resolves the same repository tag. Breaking changes to generated public APIs require a major version, additions require a minor version, and compatible fixes require a patch version.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2025 Julian Rath.

Built with [Typer](https://typer.tiangolo.com/), [Rich](https://rich.readthedocs.io/), [Pydantic](https://docs.pydantic.dev/), [uv](https://github.com/astral-sh/uv), [Ruff](https://github.com/astral-sh/ruff), and [mypy](http://mypy-lang.org/).
