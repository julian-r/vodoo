# Integration Tests

Automated integration tests that run vodoo against real Odoo instances via Docker.

## Quick Start

```bash
# Run against all community versions (17, 18, 19)
./tests/integration/run.sh

# Run a specific version
./tests/integration/run.sh 19

# Run with enterprise edition
ENTERPRISE=1 ./tests/integration/run.sh 19

# Run all versions, both editions
ENTERPRISE=1 ./tests/integration/run.sh 17 18 19

# Keep containers after tests (for debugging)
KEEP=1 ./tests/integration/run.sh 19
```

## What Gets Tested

### Community (all versions)
- **Generic CRUD** — create, read, update, delete on `res.partner`
- **Project** (`project.project`) — list, get, update, comments, notes, attachments, stages
- **Project Tasks** (`project.task`) — full CRUD, tags, subtasks, attachments
- **CRM** (`crm.lead`) — leads/opportunities, tags, attachments, comments
- **Security** — group creation, user management, password setting, group assignment

### Enterprise (requires enterprise addons)
- **Helpdesk** (`helpdesk.ticket`) — tickets, tags, comments, attachments
- **Knowledge** (`knowledge.article`) — articles, comments, notes
- **Timer/Timesheet** — start/stop timers, today's timesheets

### Transport Layer
- Verifies Odoo 17/18 use `LegacyTransport` (JSON-RPC)
- Verifies Odoo 19 uses `JSON2Transport` (JSON-2 bearer auth)

## Architecture

```
tests/integration/
├── run.sh                  # End-to-end orchestrator
├── setup_odoo.py           # DB provisioning + API key creation
├── conftest.py             # pytest fixtures and markers
├── test_suite.py           # 60 test cases across 9 classes
├── docker-compose.yml      # Parameterized compose file
├── Dockerfile.enterprise   # Builds enterprise image from addons
├── odoo.conf               # Community Odoo config
└── odoo-enterprise.conf    # Enterprise Odoo config (with addons_path)
```

## Port Mapping

| Version | Community | Enterprise |
|---------|-----------|------------|
| 17      | 17069     | 17169      |
| 18      | 18069     | 18169      |
| 19      | 19069     | 19169      |

## Enterprise Addons

The enterprise test images are built from enterprise addons directories. The runner looks for addons in this order:

1. Version-specific env var: `ENTERPRISE_ADDONS_17`, `ENTERPRISE_ADDONS_18`, etc.
2. Git worktree convention: `/tmp/enterprise-17`, `/tmp/enterprise-18`
3. Default: `ENTERPRISE_ADDONS` env var or `~/src/makespan/odoo/enterprise-addons`

To set up enterprise addons for multiple versions:

```bash
cd ~/src/makespan/odoo/enterprise-addons  # or wherever your enterprise repo is
git fetch origin 17.0 18.0 19.0
git worktree add /tmp/enterprise-17 origin/17.0
git worktree add /tmp/enterprise-18 origin/18.0
# 19.0 is assumed to be the default checkout
```

## API Key Creation

API keys cannot be created via JSON-RPC (Odoo's `@check_identity` wizard blocks it). Instead, `setup_odoo.py` runs `odoo shell` inside the Docker container to call `_generate()` directly. Key differences by version:

- **Odoo 17**: `_generate(scope, name)` — 2 args
- **Odoo 18+**: `_generate(scope, name, expiration_date)` — 3 args

The key is bound to the admin user (not `__system__`) via `with_user(admin).sudo()`.

## Environment Files

Each test run creates a `.env.test.<suffix>` file (gitignored):

```
ODOO_URL=http://localhost:19069
ODOO_DATABASE=vodoo_test_19
ODOO_USERNAME=admin
ODOO_PASSWORD=<api-key>
ODOO_MAJOR_VERSION=19
ODOO_ENTERPRISE=0
```

## Bugs Found

These bugs in vodoo were discovered and fixed by the integration tests:

1. **`transport.py`** — JSON-2 `create` used `values` param instead of `vals_list` (list), and `write` used `values` instead of `vals`
2. **`security.py`** — Used `group_ids` field which doesn't exist in Odoo 17/18 (it's `groups_id`); added `_groups_field()` auto-detect helper
