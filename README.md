# Vodoo

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)

A modern Python CLI tool for Odoo with support for helpdesk tickets, project tasks, projects, and CRM leads/opportunities. Features include comments, notes, tags, attachments, and more.

**🤖 AI-First Design**: Designed to be used with Claude Code or similar AI coding assistants to streamline Odoo workflows through natural language commands.

## Features

- 📋 Helpdesk tickets, project tasks, projects, CRM leads, and knowledge articles
- 💬 Add comments and internal notes
- 🏷️ Create, manage, and assign tags
- 📎 Upload, list, and download attachments
- 🔍 Search across text fields (name, email, phone, description)
- 🧰 Generic CRUD operations for any Odoo model
- 🎨 Rich terminal output with tables
- ⚙️ Flexible configuration via environment variables or config files
- 🔒 Type-safe with mypy strict mode
- 🚀 Modern Python tooling (uv, ruff, mypy)

## Installation

### From PyPI (recommended)

```bash
# Install via pip
pip install vodoo

# Or install via pipx (recommended for CLI tools)
pipx install vodoo

# Or run without installing using uvx (requires uv)
uvx vodoo helpdesk list
```

### From source

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

## Configuration

Create a configuration file with your Odoo credentials. The CLI looks for configuration in these locations (in order):

1. `.vodoo.env` in the current directory
2. `~/.config/vodoo/config.env`
3. `.env` in the current directory

### Configuration File Format

Create a `.env` or `.vodoo.env` file:

```bash
ODOO_URL=https://your-odoo-instance.com
ODOO_DATABASE=your_database
ODOO_USERNAME=your_username
ODOO_PASSWORD=your_password_or_api_key
ODOO_DEFAULT_USER_ID=123  # Optional: default user ID for sudo operations
```

### Environment Variables

All configuration values can also be set via environment variables with the `ODOO_` prefix:

```bash
export ODOO_URL="https://your-odoo-instance.com"
export ODOO_DATABASE="your_database"
export ODOO_USERNAME="your_username"
export ODOO_PASSWORD="your_password"
```

## Security & Service Accounts

For production use, run Vodoo with a dedicated least-privilege service account instead of a personal user. This keeps access scoped to the models your automation needs and avoids accidental exposure of customer data.

See [docs/SECURITY.md](docs/SECURITY.md) for a concise setup checklist and recommended access rules.

## Usage

### Using with Claude Code or AI Assistants

This CLI is designed to work seamlessly with AI coding assistants like Claude Code. Instead of remembering complex command syntax, you can use natural language:

**Example workflow with Claude Code:**
```
You: "Show me all tickets assigned to me that are in progress"
Claude: [runs: vodoo helpdesk list --assigned-to "Your Name" --stage "In Progress"]

You: "Add an internal note to ticket 123 saying we're waiting for customer response"
Claude: [runs: vodoo helpdesk note 123 "Waiting for customer response"]

You: "Download all attachments from ticket 456"
Claude: [runs: vodoo helpdesk attachments 456, then downloads each]
```

The CLI is designed with AI assistants in mind, providing clear command structure and helpful error messages.

### Direct CLI Usage

### Knowledge Articles

```bash
# List all articles
vodoo knowledge list

# List workspace articles only
vodoo knowledge list --category workspace

# List favorite articles
vodoo knowledge list --favorite

# Filter by name
vodoo knowledge list --name "Getting Started"

# Show article details (with content)
vodoo knowledge show 123

# Show raw HTML content
vodoo knowledge show 123 --html

# Add internal note
vodoo knowledge note 123 "Updated section on installation"

# Get article URL
vodoo knowledge url 123
```

### CRM Leads/Opportunities

```bash
# List all leads/opportunities
vodoo crm list

# Search across name, email, phone, contact, description
vodoo crm list --search "acme"
vodoo crm list -s "john@example.com"

# List only leads or opportunities
vodoo crm list --type lead
vodoo crm list --type opportunity

# Filter by stage, team, user, or partner
vodoo crm list --stage "Qualified"
vodoo crm list --team "Direct Sales"
vodoo crm list --user "John Doe"
vodoo crm list --partner "Acme Corp"

# Combine search with filters
vodoo crm list --search "software" --type opportunity --stage "Proposition"

# Show lead details
vodoo crm show 123

# Add internal note (always allowed)
vodoo crm note 123 "Followed up via phone"

# Update lead fields
vodoo crm set 123 expected_revenue=50000 probability=75

# Attach a file
vodoo crm attach 123 proposal.pdf

# Get lead URL
vodoo crm url 123
```

### Generic Model Operations

```bash
# Read records with a domain filter
vodoo model read res.partner --domain='[["email","ilike","@acme.com"]]' --field name --field email

# Create a record
vodoo model create res.partner name="Acme" email=info@acme.com

# Update a record
vodoo model update res.partner 123 phone="+123456789"

# Delete a record (requires confirmation)
vodoo model delete res.partner 123 --confirm

# Call a custom model method
vodoo model call res.partner name_search --args='["Acme"]'
```

For safety, use a least-privilege service account (see [docs/SECURITY.md](docs/SECURITY.md)).

### List Tickets

```bash
# List all tickets (default limit: 50)
vodoo helpdesk list

# Filter by stage
vodoo helpdesk list --stage "In Progress"

# Filter by partner
vodoo helpdesk list --partner "Acme Corp"

# Filter by assigned user
vodoo helpdesk list --assigned-to "John Doe"

# Set custom limit
vodoo helpdesk list --limit 100
```

### View Ticket Details

```bash
# Show detailed information for a specific ticket
vodoo helpdesk show 123
```

### Add Comments and Notes

```bash
# Add an internal note (not visible to customers)
vodoo helpdesk note 123 "This is an internal note for the team"

# Add a public comment (visible to customers)
vodoo helpdesk comment 123 "This is a public comment"

# Post as a specific user
vodoo helpdesk note 123 "Internal update" --user-id 42
vodoo helpdesk comment 123 "Admin comment" --user-id 42
```

### Manage Tags

```bash
# List all available tags
vodoo helpdesk tags

# Add a tag to a ticket
vodoo helpdesk tag 123 5
```

### Work with Attachments

```bash
# List attachments for a ticket
vodoo helpdesk attachments 123

# Download an attachment (saves to current directory with original name)
vodoo helpdesk download 456

# Download to a specific path
vodoo helpdesk download 456 --output /path/to/file.pdf

# Download to a specific directory (uses original filename)
vodoo helpdesk download 456 --output /path/to/directory/
```

## Development

### Code Quality

This project uses modern Python tooling:

- **ruff**: Fast linting and formatting
- **mypy**: Static type checking with strict mode
- **uv**: Fast dependency management

```bash
# Run ruff linting
uv run ruff check .

# Auto-fix ruff issues
uv run ruff check --fix .

# Format code
uv run ruff format .

# Run mypy type checking
uv run mypy src/vodoo
```

### Project Structure

```
vodoo/
├── src/
│   └── vodoo/
│       ├── __init__.py
│       ├── main.py       # CLI entry point with Typer commands
│       ├── client.py     # Odoo XML-RPC client wrapper
│       ├── config.py     # Configuration management
│       ├── auth.py       # Authentication and sudo utilities
│       └── helpdesk.py   # Helpdesk operations and display logic
├── pyproject.toml        # Project configuration and dependencies
├── README.md
└── .gitignore
```

## How It Works

### Odoo XML-RPC API

This tool uses Odoo's external XML-RPC API to interact with the Odoo instance. The API provides:

- Authentication via username/password or API keys
- Full CRUD operations on Odoo models
- Search and filtering capabilities
- Support for sudo operations

### Sudo Operations for Comments

Comments are posted using Odoo's `message_post` method with sudo context, allowing you to post messages as a specific user. Configure `ODOO_DEFAULT_USER_ID` to set the default user for comment operations.

### Attachment Handling

Attachments are stored in Odoo's `ir.attachment` model with base64-encoded data. The CLI automatically decodes and saves files when downloading.

## Requirements

- Python 3.12+
- Access to an Odoo instance with XML-RPC enabled
- Valid Odoo credentials (username/password or API key)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

### Development Setup

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/vodoo.git`
3. Create a feature branch: `git checkout -b feature/my-new-feature`
4. Install development dependencies: `uv sync --all-extras`
5. Make your changes
6. Run tests and checks:
   ```bash
   uv run ruff check .
   uv run ruff format .
   uv run mypy src/vodoo
   ```
7. Commit your changes: `git commit -am 'Add some feature'`
8. Push to the branch: `git push origin feature/my-new-feature`
9. Submit a pull request

### Reporting Issues

Please report issues at: https://github.com/julian-r/vodoo/issues

## Publishing to PyPI

This project is configured to automatically publish to PyPI using GitHub Actions with trusted publishing.

### Setup (One-time configuration)

1. **Configure PyPI Trusted Publisher**:
   - Go to https://pypi.org/manage/account/publishing/
   - Add a new pending publisher with these details:
     - PyPI Project Name: `vodoo`
     - Owner: `semadox`
     - Repository name: `vodoo`
     - Workflow name: `publish.yml`
     - Environment name: `pypi`

2. **Configure TestPyPI Trusted Publisher** (optional, for testing):
   - Go to https://test.pypi.org/manage/account/publishing/
   - Add the same configuration with environment name: `testpypi`

3. **Create GitHub Environments**:
   - Go to your repository settings → Environments
   - Create environment `pypi` (add protection rules if desired)
   - Create environment `testpypi` (optional)

### Releasing a new version

1. Update the version in `pyproject.toml` and `src/vodoo/__init__.py`
2. Commit the version bump: `git commit -am "Bump version to X.Y.Z"`
3. Create and push a git tag: `git tag vX.Y.Z && git push origin vX.Y.Z`
4. Create a GitHub release from the tag
5. The GitHub Action will automatically build and publish to PyPI

### Manual testing with TestPyPI

To manually trigger a test publish to TestPyPI:
```bash
# From the GitHub repository, go to Actions → Publish to PyPI → Run workflow
```

### Local build and test

```bash
# Build the package locally
uv build

# Install from local build
pip install dist/vodoo-*.whl

# Or test with TestPyPI
uv build
twine upload --repository testpypi dist/*
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2025 Semadox GmbH

## Acknowledgments

Built with:
- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [uv](https://github.com/astral-sh/uv) - Package management
- [Ruff](https://github.com/astral-sh/ruff) - Linting and formatting
- [mypy](http://mypy-lang.org/) - Type checking
