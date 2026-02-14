# API Reference

Auto-generated documentation from source code docstrings.

## Core

| Module | Description |
|--------|-------------|
| [OdooClient](client.md) | High-level sync client — delegates to the transport layer |
| [OdooConfig](config.md) | Pydantic-based configuration from env variables |
| [Transport](transport.md) | Transport abstraction (JSON-2 + legacy JSON-RPC) |
| [Exceptions](exceptions.md) | Exception hierarchy (including Odoo server-side errors) |

## Domain Modules (Sync)

| Module | Odoo Model | Description |
|--------|------------|-------------|
| [Helpdesk](helpdesk.md) | `helpdesk.ticket` | Helpdesk ticket operations (enterprise) |
| [Project Tasks](project.md) | `project.task` | Project task operations |
| [Projects](project_project.md) | `project.project` | Project operations |
| [CRM](crm.md) | `crm.lead` | CRM lead/opportunity operations |
| [Knowledge](knowledge.md) | `knowledge.article` | Knowledge article operations (enterprise) |
| [Timers](timer.md) | `account.analytic.line` | Timer and timesheet management |
| [Generic CRUD](generic.md) | *any model* | Generic model operations |
| [Security](security.md) | `res.groups` / `res.users` | Security group management |

## Shared

| Module | Description |
|--------|-------------|
| [Base Operations](base.md) | Shared CRUD, messaging, attachment helpers |
| [Auth](auth.md) | Authentication and sudo utilities |

## Async API

Vodoo provides a full async API under `vodoo.aio` with the same interface as the sync modules but using `async`/`await` and [httpx](https://www.python-httpx.org/) for non-blocking HTTP.

| Module | Description |
|--------|-------------|
| [Async Overview](async.md) | Quick start, concurrency patterns, `AsyncOdooClient` |
| [Async Helpdesk](aio/helpdesk.md) | `vodoo.aio.helpdesk` |
| [Async Project Tasks](aio/project.md) | `vodoo.aio.project` |
| [Async Projects](aio/project_project.md) | `vodoo.aio.project_project` |
| [Async CRM](aio/crm.md) | `vodoo.aio.crm` |
| [Async Knowledge](aio/knowledge.md) | `vodoo.aio.knowledge` |
| [Async Timers](aio/timer.md) | `vodoo.aio.timer` |
| [Async Generic CRUD](aio/generic.md) | `vodoo.aio.generic` |
| [Async Security](aio/security.md) | `vodoo.aio.security` |
| [Async Base](aio/base.md) | `vodoo.aio.base` |
| [Async Auth](aio/auth.md) | `vodoo.aio.auth` |
