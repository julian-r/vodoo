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
| `ODOO_HTTP_HEADERS` | Extra HTTP headers as JSON object (e.g. for reverse proxies) | `{}` |
| `ODOO_HTTP_HEADERS_CMD` | Command that derives HTTP headers | `None` |
| `ODOO_HTTP_HEADERS_CMD_OUTPUT` | Command stdout format (`json` or `token`) | `json` |
| `ODOO_HTTP_HEADERS_CMD_HEADER` | Header name used when output mode is `token` | `None` |
| `ODOO_HTTP_HEADERS_CMD_TIMEOUT` | Timeout in seconds for `ODOO_HTTP_HEADERS_CMD` | `120` |
| `ODOO_HTTP_HEADERS_CACHE_BACKEND` | Cache backend for command headers (`keyring` or `none`) | `keyring` |
| `ODOO_HTTP_HEADERS_CACHE_KEY` | Optional cache key override for command headers | auto |
| `ODOO_HTTP_HEADERS_CACHE_TTL` | Fallback cache TTL in seconds when no expiry is returned | `300` |

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

## Custom HTTP Headers

If your Odoo instance is behind a reverse proxy that requires additional headers (e.g. Cloudflare Zero Trust), set `ODOO_HTTP_HEADERS` to a JSON object. These headers are sent with every request.

```bash
ODOO_HTTP_HEADERS='{"CF-Access-Client-Id": "your-client-id.access", "CF-Access-Client-Secret": "your-client-secret"}'
```

For short-lived tokens, you can also use `ODOO_HTTP_HEADERS_CMD`.
The command is executed directly (without a shell) and must print JSON to stdout
in one of these formats:

```json
{"Header-Name": "value"}
```

or:

```json
{
  "headers": {"Header-Name": "value"},
  "expires_at": "2026-03-15T12:34:56Z"
}
```

You can also return `expires_in` (seconds) instead of `expires_at`.

By default, command-derived headers are cached in your OS keychain/keyring
(`ODOO_HTTP_HEADERS_CACHE_BACKEND=keyring`). This requires the Python `keyring` package.
Set `ODOO_HTTP_HEADERS_CACHE_BACKEND=none` to disable caching.

Vodoo automatically provides `ODOO_URL`, `ODOO_DATABASE`, and `ODOO_USERNAME`
to the command environment. You can also reference these as placeholders in the
command string (for example `{ODOO_URL}`).

### Cloudflare Zero Trust (recommended)

Use Cloudflare's short-lived user token flow with token output mode:

```bash
ODOO_HTTP_HEADERS_CMD='cloudflared access token -app={ODOO_URL}'
ODOO_HTTP_HEADERS_CMD_OUTPUT=token
ODOO_HTTP_HEADERS_CMD_HEADER=CF-Access-Token
ODOO_HTTP_HEADERS_CMD_TIMEOUT=120
```

First-time login (once per app/session):

```bash
cloudflared access login https://odoo.example.com
```

Optional auto-bootstrap (tries token, falls back to interactive login, retries token):

```bash
ODOO_HTTP_HEADERS_CMD='sh -lc "cloudflared access token -app={ODOO_URL} || (cloudflared access login {ODOO_URL} >/dev/null && cloudflared access token -app={ODOO_URL})"'
ODOO_HTTP_HEADERS_CMD_OUTPUT=token
ODOO_HTTP_HEADERS_CMD_HEADER=CF-Access-Token
ODOO_HTTP_HEADERS_CMD_TIMEOUT=120
```

Common pitfall: `ODOO_HTTP_HEADERS_CMD` is the command, while
`ODOO_HTTP_HEADERS_CMD_HEADER` must only be the header name (for example `CF-Access-Token`).

Example instance profile (`~/.config/vodoo/instances/makespan.env`):

```bash
ODOO_URL=https://odoo.makespan.com
ODOO_DATABASE=odoo_prod
ODOO_USERNAME=you@example.com
ODOO_PASSWORD=your-odoo-api-key
ODOO_HTTP_HEADERS_CMD='cloudflared access token -app={ODOO_URL}'
ODOO_HTTP_HEADERS_CMD_OUTPUT=token
ODOO_HTTP_HEADERS_CMD_HEADER=CF-Access-Token
ODOO_HTTP_HEADERS_CMD_TIMEOUT=120
ODOO_HTTP_HEADERS_CACHE_BACKEND=keyring
ODOO_HTTP_HEADERS_CACHE_TTL=300
```

If both `ODOO_HTTP_HEADERS_CMD` and `ODOO_HTTP_HEADERS` are set, explicit
`ODOO_HTTP_HEADERS` values win on key conflicts.

This is provider-agnostic and works with any proxy or middleware that expects custom headers.

### Troubleshooting Cloudflare Access

If you see a `302 Found` redirect to `*.cloudflareaccess.com/cdn-cgi/access/login/...`,
Vodoo reached Cloudflare without a valid Access token.

Checklist:

1. Ensure command variables are correct:
   - `ODOO_HTTP_HEADERS_CMD` contains the command
   - `ODOO_HTTP_HEADERS_CMD_OUTPUT=token`
   - `ODOO_HTTP_HEADERS_CMD_HEADER=CF-Access-Token`
2. Run one-time login:
   - `cloudflared access login https://your-odoo-host`
3. Verify token command manually:
   - `cloudflared access token -app=https://your-odoo-host`
4. Increase timeout for interactive flows:
   - `ODOO_HTTP_HEADERS_CMD_TIMEOUT=120` (or higher)
5. If needed, use auto-bootstrap fallback command shown above.

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
