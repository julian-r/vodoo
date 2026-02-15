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
│   ├── client.py             # OdooClient (sync) + namespace wiring
│   ├── transport.py          # Sync transport (JSON-RPC / JSON-2, httpx)
│   ├── config.py             # Pydantic configuration
│   ├── exceptions.py         # Exception hierarchy (incl. Odoo server errors)
│   ├── auth.py               # Authentication / sudo
│   ├── _domain.py            # DomainNamespace base class (CRUD, messaging, tags, attachments)
│   ├── base.py               # Field constants, display helpers
│   ├── helpdesk.py           # HelpdeskNamespace (DomainNamespace subclass)
│   ├── project_tasks.py      # TaskNamespace
│   ├── projects.py           # ProjectNamespace
│   ├── crm.py                # CrmNamespace
│   ├── knowledge.py          # KnowledgeNamespace
│   ├── generic.py            # GenericNamespace
│   ├── security.py           # SecurityNamespace
│   ├── timer.py              # TimerNamespace
│   └── aio/                  # Async API (mirrors sync modules)
│       ├── __init__.py       # AsyncOdooClient export
│       ├── client.py         # AsyncOdooClient + namespace wiring
│       ├── transport.py      # Async transport (httpx)
│       ├── auth.py           # Async auth / sudo
│       ├── _domain.py        # AsyncDomainNamespace base class
│       ├── helpdesk.py       # Async HelpdeskNamespace
│       ├── project_tasks.py  # Async TaskNamespace
│       ├── projects.py
│       ├── crm.py            # Async CrmNamespace
│       ├── knowledge.py      # Async KnowledgeNamespace
│       ├── generic.py        # Async GenericNamespace
│       ├── security.py       # Async SecurityNamespace
│       └── timer.py          # Async TimerNamespace
├── tests/integration/        # Docker-based integration tests
├── docs/                     # MkDocs documentation
├── mkdocs.yml                # MkDocs Material + mike versioning
└── pyproject.toml
```

## Versioning

The version is derived from **git tags** via `hatch-vcs` — there is no hardcoded version string anywhere.

- `pyproject.toml` uses `dynamic = ["version"]`
- `__init__.py` reads the version at runtime via `importlib.metadata`
- `_version.py` is auto-generated at build time (gitignored)

To release: just create a tag and push it. See [Releasing](#releasing) below.

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

# Build in strict mode (fails on warnings)
uv run mkdocs build --strict
```

Documentation is versioned with [mike](https://github.com/jimporter/mike) and deployed to GitHub Pages on each release.

## Releasing

1. Create and push a git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
2. Create a GitHub release from the tag
3. GitHub Actions automatically: builds package → publishes to PyPI → deploys versioned docs

## Reporting Issues

Please report issues at: [github.com/julian-r/vodoo/issues](https://github.com/julian-r/vodoo/issues)
