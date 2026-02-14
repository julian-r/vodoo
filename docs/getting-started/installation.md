# Installation

## From PyPI (recommended)

=== "pip"

    ```bash
    pip install vodoo
    ```

=== "pipx (isolated CLI)"

    ```bash
    pipx install vodoo
    ```

=== "uvx (run without installing)"

    ```bash
    uvx vodoo helpdesk list
    ```

## From Source

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Clone the repository
git clone https://github.com/julian-r/vodoo.git
cd vodoo

# Install dependencies
uv sync

# Install in development mode with dev dependencies
uv sync --all-extras

# Install the CLI tool
uv pip install -e .
```

## Verify Installation

```bash
vodoo --help
```

You should see the list of available subcommands: `helpdesk`, `project-task`, `project`, `crm`, `knowledge`, `timer`, `model`, `security`.

## Requirements

- **Python 3.12+**
- Access to an Odoo instance (14–19) with JSON-RPC or JSON-2 API enabled
- Valid Odoo credentials (username/password or API key)

## Optional Dependencies

Install extra dependency groups for development or documentation:

```bash
# Development tools (ruff, mypy, pytest)
pip install vodoo[dev]

# Documentation (mkdocs-material)
pip install vodoo[docs]
```
