# Configuration

Vodoo loads configuration from environment variables and `.env`-style files using [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/).

## Configuration Sources

Files are checked in this order (first match wins):

1. `~/.config/vodoo/config.env` — recommended for credentials (outside project dirs)
2. `.vodoo.env` — project-specific config
3. `.env` — generic dotenv fallback

Environment variables always take precedence over file values.

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
| `ODOO_DEFAULT_USER_ID` | Default user ID for sudo/comment operations | `None` |
| `ODOO_RETRY_COUNT` | Maximum retries for transient errors | `2` |
| `ODOO_RETRY_BACKOFF` | Base backoff delay in seconds (exponential) | `0.5` |
| `ODOO_RETRY_MAX_BACKOFF` | Maximum backoff delay in seconds | `30.0` |

## Example Config File

Create `~/.config/vodoo/config.env`:

```bash
ODOO_URL=https://my-instance.odoo.com
ODOO_DATABASE=production
ODOO_USERNAME=bot@example.com
ODOO_PASSWORD=your-api-key-here
ODOO_DEFAULT_USER_ID=42
```

!!! tip "Use API keys over passwords"
    Odoo 14+ supports API keys. They are safer than passwords because they
    can be scoped and revoked independently. Generate one under
    *Settings → Users → API Keys*.

!!! warning "HTTPS in production"
    Vodoo warns when `ODOO_URL` does not use `https://`. Credentials are
    sent in cleartext over HTTP — only use it for local development.

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

## Security Recommendations

- Store credentials in `~/.config/vodoo/config.env` (not inside project directories)
- Use a dedicated [service account](../development/security.md) with least-privilege groups
- Never commit `.env` files to version control
- Rotate API keys periodically
