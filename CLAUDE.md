# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vodoo is a Python CLI tool for interacting with Odoo via JSON-RPC (Odoo 14-18) and JSON-2 (Odoo 19+). It supports helpdesk tickets, project tasks, projects, CRM leads/opportunities, knowledge articles, and timesheets.

## Commands

```bash
# Install dependencies
uv sync --all-extras

# Run the CLI during development
uv run vodoo helpdesk list
uv run vodoo project-task list
uv run vodoo project list
uv run vodoo crm list

# Linting
uv run ruff check .
uv run ruff check --fix .

# Formatting
uv run ruff format .

# Type checking
uv run mypy src/vodoo

# Build package
uv build

# Documentation (MkDocs Material + mike versioning)
uv sync --extra docs
uv run mkdocs serve          # local dev server at http://127.0.0.1:8000
uv run mkdocs build          # build static site to site/
uv run mkdocs build --strict # strict mode (fail on warnings)
uv run mike serve            # serve versioned docs locally
```

## Architecture

### Module Structure

- **client.py** - High-level client delegating to the transport layer
- **config.py** - Pydantic-based configuration from environment variables/.env files
- **auth.py** - Authentication utilities and sudo operations
- **base.py** - Shared operations (CRUD, display, attachments, messages) used by all domain modules
- **helpdesk.py** - Helpdesk ticket operations (model: `helpdesk.ticket`)
- **project.py** - Project task operations (model: `project.task`)
- **project_project.py** - Project operations (model: `project.project`)
- **crm.py** - CRM lead/opportunity operations (model: `crm.lead`)
- **generic.py** - Generic CRUD operations for any Odoo model
- **security.py** - Security group utilities and service-account helpers
- **main.py** - Typer CLI with subcommands: `helpdesk`, `project-task`, `project`, `crm`, `model`, `security`

### Design Pattern

Domain modules delegate to `base.py` functions with a MODEL constant:
```python
MODEL = "helpdesk.ticket"
def add_comment(client, ticket_id, message, ...):
    return base_add_comment(client, MODEL, ticket_id, message, ...)
```

### Configuration

Loads from (in order): `~/.config/vodoo/config.env`, `.vodoo.env`, `.env`

Required: `ODOO_URL`, `ODOO_DATABASE`, `ODOO_USERNAME`, `ODOO_PASSWORD`
Optional: `ODOO_DEFAULT_USER_ID`

Recommended: Use `~/.config/vodoo/config.env` for credentials (outside project dirs).

## Versioning

Version is derived from **git tags** via `hatch-vcs` — single source of truth.

- **Do not** hardcode version strings anywhere
- `__init__.py` reads version at runtime via `importlib.metadata`
- `_version.py` is auto-generated at build time (gitignored)
- To release: `git tag v0.4.0 && git push origin v0.4.0` → create GitHub release

## Code Style

- Python 3.12+ with strict mypy typing
- ruff for linting/formatting (line length: 100)
- All functions must have type hints
- Use `Path` objects for file operations
- Rich library for terminal output
