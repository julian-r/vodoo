# Integration Tests

Automated integration tests that run vodoo against real Odoo instances via Docker.

## Quick Start

```bash
# Run against all community versions (17, 18, 19)
./tests/integration/run.sh

# Run a specific version
./tests/integration/run.sh 19

# Run with Enterprise (after creating the authorized checkout below)
ENTERPRISE=1 ENTERPRISE_ADDONS_19=~/src/odoo-enterprise-19 \
  ./tests/integration/run.sh 19

# Run all versions, both editions (set all three ENTERPRISE_ADDONS_<version> paths)
ENTERPRISE=1 \
ENTERPRISE_ADDONS_17=~/src/odoo-enterprise-17 \
ENTERPRISE_ADDONS_18=~/src/odoo-enterprise-18 \
ENTERPRISE_ADDONS_19=~/src/odoo-enterprise-19 \
  ./tests/integration/run.sh 17 18 19

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

There is no public official Odoo Enterprise Docker image. Enterprise consists of proprietary addons from the private [`odoo/enterprise`](https://github.com/odoo/enterprise) repository and requires an eligible Odoo subscription or partner account.

Vodoo deliberately does not clone, vendor, or publish that source. The local runner accepts only a clean Git checkout whose `origin` is the official repository and verifies `HEAD` against the live private `origin/<version>.0` branch. It exports tracked files with `git archive`, so `.git`, credentials, ignored files, and untracked files cannot enter the Docker build context.

The licensed source remains in the resulting local image and may remain in Docker's local build cache. Temporary exports are removed on success, failure, and interruption. If local policy requires complete removal after testing, remove the image and prune the affected builder cache; note that `docker builder prune` can remove unrelated build cache too.

### Clone an official version

Authenticate GitHub CLI with an account entitled to the private repository, then clone only the version being tested:

```bash
gh auth status
gh auth setup-git
gh repo view odoo/enterprise

gh repo clone odoo/enterprise ~/src/odoo-enterprise-19 \
  -- --branch 19.0 --single-branch --depth 1
```

Use a separate checkout for each major version:

```bash
gh repo clone odoo/enterprise ~/src/odoo-enterprise-17 \
  -- --branch 17.0 --single-branch --depth 1
gh repo clone odoo/enterprise ~/src/odoo-enterprise-18 \
  -- --branch 18.0 --single-branch --depth 1
```

### Validate and build locally

Build the image without starting Odoo or running tests:

```bash
ENTERPRISE_BUILD_ONLY=1 \
ENTERPRISE_ADDONS_19=~/src/odoo-enterprise-19 \
./tests/integration/run.sh 19
```

The result is tagged only in the local Docker daemon as `vodoo-odoo-ee:19.0`. The image records the validated source commit in `com.vodoo.enterprise.commit` and is never pushed by the runner.

Inspect its provenance:

```bash
docker image inspect vodoo-odoo-ee:19.0 \
  --format '{{ json .Config.Labels }}'
```

Run Community and Enterprise tests together:

```bash
ENTERPRISE=1 \
ENTERPRISE_ADDONS_19=~/src/odoo-enterprise-19 \
./tests/integration/run.sh 19
```

For the complete matrix:

```bash
ENTERPRISE=1 \
ENTERPRISE_ADDONS_17=~/src/odoo-enterprise-17 \
ENTERPRISE_ADDONS_18=~/src/odoo-enterprise-18 \
ENTERPRISE_ADDONS_19=~/src/odoo-enterprise-19 \
./tests/integration/run.sh 17 18 19
```

The runner resolves Enterprise source in this order:

1. `ENTERPRISE_ADDONS_<version>` (recommended)
2. `/tmp/enterprise-<version>` worktree convention
3. `ENTERPRISE_ADDONS` fallback

The build recipe always runs with `--pull`; Docker may reuse matching local layers. Never push these images to a public registry: their layers contain licensed Enterprise source.

Remove the local image when it is no longer needed:

```bash
docker image rm vodoo-odoo-ee:19.0
# Optional and broader: remove unused Docker build cache as well.
docker builder prune
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
