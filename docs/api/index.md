# API Reference

Auto-generated documentation from source code docstrings.

## Core

| Module | Description |
|--------|-------------|
| [OdooClient](client.md) | High-level client — delegates to the transport layer |
| [OdooConfig](config.md) | Pydantic-based configuration from env variables |
| [Transport](transport.md) | Transport abstraction (JSON-2 + legacy JSON-RPC) |
| [Exceptions](exceptions.md) | Exception hierarchy |

## Domain Modules

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
