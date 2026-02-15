# API Reference

Auto-generated documentation from source code docstrings.

## Core

| Module | Description |
|--------|-------------|
| [OdooClient](client.md) | High-level sync client with domain namespaces |
| [OdooConfig](config.md) | Pydantic-based configuration from env variables |
| [Transport](transport.md) | Transport abstraction (JSON-2 + legacy JSON-RPC) |
| [Exceptions](exceptions.md) | Exception hierarchy (including Odoo server-side errors) |

## Domain Namespaces (Sync)

Domain operations are accessed as namespaces on the client (e.g. `client.helpdesk.list()`).

| Namespace | Odoo Model | Description |
|-----------|------------|-------------|
| [`client.helpdesk`](helpdesk.md) | `helpdesk.ticket` | Helpdesk ticket operations (enterprise) |
| [`client.tasks`](project_tasks.md) | `project.task` | Project task operations |
| [`client.projects`](projects.md) | `project.project` | Project operations |
| [`client.crm`](crm.md) | `crm.lead` | CRM lead/opportunity operations |
| [`client.knowledge`](knowledge.md) | `knowledge.article` | Knowledge article operations (enterprise) |
| [`client.timer`](timer.md) | `account.analytic.line` | Timer and timesheet management |
| [`client.generic`](generic.md) | *any model* | Generic model operations |
| [`client.security`](security.md) | `res.groups` / `res.users` | Security group management |

## Shared

| Module | Description |
|--------|-------------|
| [Base Operations](base.md) | Shared CRUD, messaging, attachment helpers (base class for domain namespaces) |
| [Auth](auth.md) | Authentication and sudo utilities |

## Async API

Vodoo provides a full async API via `AsyncOdooClient` with the same namespace interface as the sync client but using `async`/`await` and [httpx](https://www.python-httpx.org/) for non-blocking HTTP.

| Module | Description |
|--------|-------------|
| [Async Overview](async.md) | Quick start, concurrency patterns, `AsyncOdooClient` |
| [Async Helpdesk](aio/helpdesk.md) | `AsyncHelpdeskNamespace` |
| [Async Project Tasks](aio/project_tasks.md) | `AsyncTaskNamespace` |
| [Async Projects](aio/projects.md) | `AsyncProjectNamespace` |
| [Async CRM](aio/crm.md) | `AsyncCRMNamespace` |
| [Async Knowledge](aio/knowledge.md) | `AsyncKnowledgeNamespace` |
| [Async Timers](aio/timer.md) | `AsyncTimerNamespace` |
| [Async Generic CRUD](aio/generic.md) | `AsyncGenericNamespace` |
| [Async Security](aio/security.md) | `AsyncSecurityNamespace` |
| [Async Base](aio/base.md) | `AsyncDomainNamespace` base class |
| [Async Auth](aio/auth.md) | Async authentication utilities |
