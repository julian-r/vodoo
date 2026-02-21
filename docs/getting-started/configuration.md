# Configuration

Vodoo loads configuration from environment variables and `.env`-style files using [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Configuration Sources

### Instance-aware mode (new)

When an instance is selected (via `--instance`, `VODOO_INSTANCE`, or a `default-instance` file),
Vodoo checks these files first:

1. `.vodoo/instances/<instance>.env` (project-local override)
2. `~/.config/vodoo/instances/<instance>.env` (global)

### Legacy fallback mode

If no explicit instance is selected and no instance file is found, Vodoo falls back to:

1. `.vodoo.env`
2. `.env`
3. `~/.config/vodoo/config.env`

Environment variables always take precedence over file values.

## Selecting an Instance

Priority order:

1. CLI: `vodoo --instance prod ...`
2. Env var: `VODOO_INSTANCE=prod`
3. Project default: `.vodoo/default-instance`
4. Global default: `~/.config/vodoo/default-instance`
5. Fallback: `default`

If you explicitly select an instance (`--instance` or `VODOO_INSTANCE`) and no matching
profile exists, Vodoo raises a configuration error instead of silently using legacy files.

### Helpful CLI commands

```bash
vodoo config list-instances
vodoo config show
vodoo config use staging
vodoo config use prod --global
vodoo config test --instance staging
```

## Required Settings

| Variable | Description | Example |
|----------|-------------|---------|
| `ODOO_URL` | Odoo instance URL | `https://my.odoo.com` |
| `ODOO_DATABASE` | Database name | `production` |
| `ODOO_USERNAME` | Login username | `bot@example.com` |
| `ODOO_PASSWORD` | Password or API key | `abc123...` |

## Optional Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `ODOO_PASSWORD_REF` | Secret reference (for example `op://Vault/Item/password`) | `None` |
| `ODOO_DEFAULT_USER_ID` | Default user ID for sudo/comment operations | `None` |
| `ODOO_RETRY_COUNT` | Maximum retries for transient errors | `2` |
| `ODOO_RETRY_BACKOFF` | Base backoff delay in seconds (exponential) | `0.5` |
| `ODOO_RETRY_MAX_BACKOFF` | Maximum backoff delay in seconds | `30.0` |

## Example Config Files

### Single profile (legacy)

`~/.config/vodoo/config.env`:

```bash
ODOO_URL=https://my-instance.odoo.com
ODOO_DATABASE=production
ODOO_USERNAME=bot@example.com
ODOO_PASSWORD=your-api-key-here
ODOO_DEFAULT_USER_ID=42
```

### Multi-instance

`~/.config/vodoo/instances/prod.env`:

```bash
ODOO_URL=https://prod.odoo.com
ODOO_DATABASE=production
ODOO_USERNAME=bot@example.com
ODOO_PASSWORD_REF=op://Engineering/Vodoo Prod/password
```

`~/.config/vodoo/default-instance`:

```text
prod
```

!!! tip "Use API keys over passwords"
    Odoo 14+ supports API keys. They are safer than passwords because they
    can be scoped and revoked independently. Generate one under
    *Settings → Users → API Keys*.

!!! warning "HTTPS in production"
    Vodoo warns when `ODOO_URL` does not use `https://`. Credentials are
    sent in cleartext over HTTP — only use it for local development.

## 1Password Secrets (`op://`)

Set `ODOO_PASSWORD_REF` to a 1Password secret reference:

```bash
ODOO_PASSWORD_REF=op://Engineering/Vodoo Prod/password
```

Vodoo resolves this by calling:

```bash
op read op://Engineering/Vodoo\ Prod/password
```

Requirements:

- 1Password CLI (`op`) must be installed
- You must be signed in (`op signin`)

If `ODOO_PASSWORD_REF` is set, it takes precedence over `ODOO_PASSWORD`.

## Programmatic Configuration

When using Vodoo as a library, pass configuration directly:

```python
from vodoo import OdooClient, OdooConfig

config = OdooConfig(
    url="https://my.odoo.com",
    database="mydb",
    username="bot@example.com",
    password="api-key",
)
client = OdooClient(config)
```

Or load from a specific file:

```python
from pathlib import Path
from vodoo import OdooConfig

config = OdooConfig.from_file(Path("/etc/vodoo/config.env"))
```

Load a specific instance:

```python
from vodoo import OdooConfig

config = OdooConfig.from_file(instance="staging")
```

## Security Recommendations

- Store credentials in `~/.config/vodoo` (not inside project directories)
- Prefer `ODOO_PASSWORD_REF` over plain-text passwords
- Use a dedicated [service account](../development/security.md) with least-privilege groups
- Never commit `.env` files to version control
- Rotate API keys periodically
