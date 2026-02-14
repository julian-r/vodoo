# Vodoo

**Modern Python library and CLI for Odoo**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![PyPI](https://img.shields.io/pypi/v/vodoo)](https://pypi.org/project/vodoo/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

---

Vodoo is a typed Python library and CLI for interacting with Odoo instances via JSON-RPC (Odoo 17–18) and JSON-2 (Odoo 19+). It covers helpdesk tickets, project tasks, projects, CRM leads/opportunities, knowledge articles, and timesheets.

## :rocket: Highlights

- **Dual-use** — works as a CLI tool *and* as an importable Python library
- **Sync + Async** — full async API under `vodoo.aio` with httpx
- **Auto-detecting transport** — JSON-2 for Odoo 19+ (~3-4× faster), legacy JSON-RPC for 17–18
- **AI-first design** — clear command structure for Claude Code and similar assistants
- **Fully typed** — strict mypy, Pydantic models, rich terminal output
- **Comprehensive** — CRUD, comments, notes, tags, attachments, timers, security groups
- **Rich exceptions** — Odoo server errors mapped to typed Python exceptions

## Odoo Version Support

| Version | Protocol | Status |
|---------|----------|--------|
| Odoo 17 | Legacy JSON-RPC | :white_check_mark: Fully tested |
| Odoo 18 | Legacy JSON-RPC | :white_check_mark: Fully tested |
| Odoo 19 | JSON-2 (bearer auth) | :white_check_mark: Fully tested |

## Quick Example

=== "CLI"

    ```bash
    # List helpdesk tickets
    vodoo helpdesk list --stage "In Progress"

    # Add a comment to a CRM lead
    vodoo crm comment 42 "Following up on the proposal"

    # Start a timer on a task
    vodoo timer start 15
    ```

=== "Python Library"

    ```python
    from vodoo import OdooClient, OdooConfig

    config = OdooConfig(
        url="https://my.odoo.com",
        database="mydb",
        username="bot@example.com",
        password="api-key-here",
    )
    client = OdooClient(config)

    # Search partners
    partners = client.search_read(
        "res.partner",
        domain=[["email", "ilike", "@acme.com"]],
        fields=["name", "email"],
        limit=10,
    )

    # Use domain helpers
    from vodoo.helpdesk import list_tickets
    tickets = list_tickets(client, limit=5)
    ```

## What's Next?

<div class="grid cards" markdown>

-   :material-download:{ .lg .middle } **Install Vodoo**

    ---

    Install via pip, pipx, or uvx in under a minute.

    [:octicons-arrow-right-24: Installation](getting-started/installation.md)

-   :material-cog:{ .lg .middle } **Configure**

    ---

    Set up credentials and connect to your Odoo instance.

    [:octicons-arrow-right-24: Configuration](getting-started/configuration.md)

-   :material-console:{ .lg .middle } **CLI Reference**

    ---

    All commands, options, and examples.

    [:octicons-arrow-right-24: CLI Reference](cli/index.md)

-   :material-language-python:{ .lg .middle } **API Reference**

    ---

    Auto-generated from source — every class, function, and type.

    [:octicons-arrow-right-24: API Reference](api/index.md)

</div>
