# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Vodoo is a Python CLI tool for interacting with Odoo via JSON-RPC (Odoo 17-18) and JSON-2 (Odoo 19+). It supports helpdesk tickets, project tasks, projects, CRM leads/opportunities, knowledge articles, and timesheets.

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

# Integration tests (requires Docker)
./tests/integration/run.sh                    # all community editions (17, 18, 19)
./tests/integration/run.sh 19                 # community 19 only
./tests/integration/run.sh 17 18              # community 17 + 18
ENTERPRISE=1 ./tests/integration/run.sh 19    # also run enterprise 19
KEEP=1 ./tests/integration/run.sh 19          # don't tear down containers

# Unit tests
uv run pytest tests/test_exceptions.py -v

# Documentation (MkDocs Material + mike versioning)
uv sync --extra docs
uv run python scripts/gen_cli_docs.py  # regenerate CLI reference from Typer app
uv run mkdocs serve          # local dev server at http://127.0.0.1:8000
uv run mkdocs build          # build static site to site/
uv run mkdocs build --strict # strict mode (fail on warnings)
uv run mike serve            # serve versioned docs locally
```

## Architecture

### Module Structure

- **client.py** - OdooClient (sync) with domain namespace properties (`client.helpdesk`, `.crm`, etc.)
- **transport.py** - Transport abstraction (JSON-2 + legacy JSON-RPC)
- **config.py** - Pydantic-based configuration from environment variables/.env files
- **exceptions.py** - Exception hierarchy (VodooError and subclasses)
- **auth.py** - Authentication utilities and sudo operations
- **_domain.py** - `DomainNamespace` base class (CRUD, messaging, tags, attachments)
- **base.py** - Field constants and display helpers (`display_records`, `display_record_detail`)
- **helpdesk.py** - `HelpdeskNamespace` (DomainNamespace subclass, model: `helpdesk.ticket`)
- **project.py** - `TaskNamespace` (model: `project.task`)
- **project_project.py** - `ProjectNamespace` (model: `project.project`)
- **crm.py** - `CrmNamespace` (model: `crm.lead`)
- **knowledge.py** - `KnowledgeNamespace` (model: `knowledge.article`)
- **timer.py** - `TimerNamespace` (start, stop, status)
- **generic.py** - `GenericNamespace` (CRUD for any Odoo model)
- **security.py** - `SecurityNamespace` (group creation, user management)
- **main.py** - Typer CLI with subcommands: `helpdesk`, `project-task`, `project`, `crm`, `knowledge`, `model`, `security`, `timer`
- **aio/** - Async mirrors: `AsyncOdooClient`, `AsyncDomainNamespace` subclasses

### Design Pattern
Domain modules are `DomainNamespace` subclasses exposed as attributes on the client:
```python
client.helpdesk.list(limit=10)
client.helpdesk.get(42)
client.helpdesk.comment(42, "Deployed to staging")

# Async:
await client.helpdesk.list(limit=10)
```
Subclasses set `_model`, `_default_fields`, `_tag_model` etc. and add domain-specific methods (e.g. `create`). Display functions remain module-level: `from vodoo.helpdesk import display_tickets`.

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

## GitHub

Use `gh` CLI for all GitHub interactions (issues, PRs, releases, etc.):

```bash
gh issue list
gh issue view 14
gh issue comment 14 --body "comment text"
gh pr create --title "..." --body "..."
gh pr list
gh release create v0.4.0 --generate-notes
```

Do NOT use browser automation for GitHub — `gh` is authenticated and faster.

## Code Style

- Python 3.12+ with strict mypy typing
- ruff for linting/formatting (line length: 100)
- All functions must have type hints
- Use `Path` objects for file operations
- Rich library for terminal output
