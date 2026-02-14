# Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Development Setup

1. **Fork** the repository
2. **Clone** your fork:
   ```bash
   git clone https://github.com/YOUR_USERNAME/vodoo.git
   cd vodoo
   ```
3. **Install** development dependencies:
   ```bash
   uv sync --all-extras
   ```
4. **Create** a feature branch:
   ```bash
   git checkout -b feature/my-new-feature
   ```

## Code Quality

Run all checks before submitting:

```bash
# Linting
uv run ruff check .

# Auto-fix lint issues
uv run ruff check --fix .

# Formatting
uv run ruff format .

# Type checking
uv run mypy src/vodoo
```

## Code Style

- **Python 3.12+** with strict mypy typing
- **ruff** for linting and formatting (line length: 100)
- All functions must have **type hints**
- Use `Path` objects for file operations
- Use **Rich** for terminal output
- **Google-style docstrings** for all public functions

## Project Structure

```
vodoo/
├── src/vodoo/
│   ├── __init__.py           # Public API exports
│   ├── main.py               # CLI entry point (Typer)
│   ├── client.py             # OdooClient
│   ├── transport.py          # Transport layer (JSON-RPC / JSON-2)
│   ├── config.py             # Pydantic configuration
│   ├── exceptions.py         # Exception hierarchy
│   ├── auth.py               # Authentication / sudo
│   ├── base.py               # Shared CRUD / messaging helpers
│   ├── helpdesk.py           # Helpdesk operations
│   ├── project.py            # Project task operations
│   ├── project_project.py    # Project operations
│   ├── crm.py                # CRM operations
│   ├── knowledge.py          # Knowledge articles
│   ├── generic.py            # Generic model CRUD
│   ├── security.py           # Security groups
│   └── timer.py              # Timers / timesheets
├── tests/integration/        # Docker-based integration tests
├── docs/                     # MkDocs documentation
├── pyproject.toml
└── mkdocs.yml
```

## Submitting Changes

1. Commit your changes: `git commit -am 'Add some feature'`
2. Push to your branch: `git push origin feature/my-new-feature`
3. Open a **Pull Request** against `main`

## Building Documentation

```bash
# Install doc dependencies
uv sync --extra docs

# Serve locally with hot-reload
uv run mkdocs serve

# Build static site
uv run mkdocs build
```

## Reporting Issues

Please report issues at: [github.com/julian-r/vodoo/issues](https://github.com/julian-r/vodoo/issues)
