# Integration Tests

Automated integration tests that run vodoo against real Odoo instances via Docker.

## Quick Start

```bash
# Run against all community versions (17, 18, 19)
./tests/integration/run.sh

# Run a specific version
./tests/integration/run.sh 19

# Download the authorized Enterprise sources, then test one version
uv run python tests/integration/fetch_enterprise.py fetch 19
ENTERPRISE=1 ./tests/integration/run.sh 19

# Download and test the complete Community + Enterprise matrix
uv run python tests/integration/fetch_enterprise.py fetch 17 18 19
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
- **Documents** (`documents.document`) — folders, upload, download, and cleanup
- **Timer/Timesheet** — start/stop timers, today's timesheets

### Transport Layer
- Verifies Odoo 17/18 use `LegacyTransport` (JSON-RPC)
- Verifies Odoo 19 uses `JSON2Transport` (JSON-2 bearer auth)

### Native TypeScript coverage

Vitest reports each behavior independently rather than bundling a namespace into one smoke test:

- **Community:** 75 live scenarios per Odoo version
- **Enterprise:** 107 live scenarios per Odoo version

The TypeScript suite uses the same provisioned instances as Python while retaining Worker-safe `Uint8Array` binary APIs and native `Date` assertions.

### Cross-language conformance

Python and TypeScript independently consume `conformance/fixtures/v1.json`. The hermetic conformance suites verify canonical JSON-RPC and JSON-2 requests, response normalization, and typed error mapping without treating either implementation as the oracle. Date and binary rows are neutral cross-runtime vectors: TypeScript exercises its production codecs, while Python uses an explicitly test-local stdlib adapter because it has no standalone public codec API.

```bash
uv run pytest tests/conformance -q
pnpm --dir packages/typescript test
```

## Architecture

```
tests/integration/
├── run.sh                  # End-to-end orchestrator
├── setup_odoo.py           # DB provisioning + API key creation
├── conftest.py             # pytest fixtures and markers
├── test_suite.py           # Synchronous Python live scenarios
├── test_async_suite.py     # Async Python live scenarios
├── docker-compose.yml      # Parameterized compose file
├── Dockerfile.enterprise   # Builds a local image from validated Enterprise source
├── fetch_enterprise.py     # Secure official-download client and archive validator
├── odoo.conf               # Community Odoo config
└── odoo-enterprise.conf    # Enterprise Odoo config (with addons_path)

packages/typescript/test/integration/
└── odoo.integration.ts     # Native Vitest live scenarios

conformance/fixtures/
└── v1.json                 # Shared normative cross-language contract
```

## Port Mapping

| Version | Community | Enterprise |
|---------|-----------|------------|
| 17      | 17069     | 17169      |
| 18      | 18069     | 18169      |
| 19      | 19069     | 19169      |

## Enterprise Addons

There is no public official Odoo Enterprise Docker image. Enterprise is proprietary software and requires an eligible Odoo subscription. Vodoo supports the official source distributions from `odoo.com` and, as a fallback, an authorized checkout of the private [`odoo/enterprise`](https://github.com/odoo/enterprise) repository.

Vodoo never commits, uploads, or publishes the credential or source. The licensed source remains in the resulting local image and may remain in Docker's local build cache. Never push the image to a public registry.

### Store the download credential

Store the Odoo download code as the only line in `.odoo-license` at the repository root. Both this file and `.odoo-enterprise/` are Git-ignored.

```bash
umask 077
IFS= read -rsp 'Odoo download code: ' ODOO_DOWNLOAD_CODE
printf '\n'
printf '%s' "$ODOO_DOWNLOAD_CODE" > .odoo-license
unset ODOO_DOWNLOAD_CODE
chmod 600 .odoo-license
```

### Fetch official source distributions

```bash
uv run python tests/integration/fetch_enterprise.py fetch 17 18 19
```

The downloader:

- reads `.odoo-license` without printing it;
- exchanges it only with `https://www.odoo.com/thanks/download`;
- accepts the signed payload only from `https://download.odoocdn.com`;
- streams each archive into a private temporary file;
- rejects unsafe paths, links, special files, wrong major versions, malformed package metadata, and incomplete distributions;
- calculates and reports a SHA-256 provenance digest; and
- atomically stores validated archives under `.odoo-enterprise/` with mode `0600`.

Existing archives are validated and reused. Pass `--force` to download a fresh source snapshot.

### Build and test locally

Build without starting Odoo:

```bash
ENTERPRISE_BUILD_ONLY=1 ./tests/integration/run.sh 17 18 19
```

Run the complete regression matrix:

```bash
ENTERPRISE=1 ./tests/integration/run.sh 17 18 19
```

The resulting images are local tags such as `vodoo-odoo-ee:19.0`. Their labels record `com.vodoo.enterprise.source-kind` and the source archive SHA-256 in `com.vodoo.enterprise.revision`:

```bash
docker image inspect vodoo-odoo-ee:19.0 \
  --format '{{ json .Config.Labels }}'
```

The build installs the complete official Enterprise distribution over the matching official Community image. It always executes with `--pull`, although Docker may reuse matching local layers.

### Private Git fallback

An official Git checkout remains supported. Set `ENTERPRISE_ADDONS_<version>` to a clean checkout whose `origin` is `odoo/enterprise`. The runner verifies `HEAD` against the live private `origin/<version>.0` branch and exports only tracked files with `git archive`.

```bash
ENTERPRISE_ADDONS_19=~/src/odoo-enterprise-19 \
ENTERPRISE_BUILD_ONLY=1 ./tests/integration/run.sh 19
```

Source resolution order is:

1. `ENTERPRISE_ADDONS_<version>`, `/tmp/enterprise-<version>`, or `ENTERPRISE_ADDONS`;
2. `ENTERPRISE_ARCHIVE_<version>`; and
3. `.odoo-enterprise/odoo-<version>e-source.tar.gz`.

### CI credential

The `ODOO_ENTERPRISE_KEY` secret in the `enterprise-ci` GitHub environment supplies the credential to the Enterprise matrix. That environment has a custom deployment policy permitting only the `main` branch, and the job also runs only on `push`; the secret is unavailable to pull-request refs. The credential is deliberately not stored as a repository-level secret. Each job downloads one version and removes its credential, archive, image, containers, and unused Docker build cache afterward.

Set or rotate the environment secret without displaying it:

```bash
gh secret set ODOO_ENTERPRISE_KEY --env enterprise-ci < .odoo-license
```

### Cleanup

```bash
docker image rm vodoo-odoo-ee:17.0 vodoo-odoo-ee:18.0 vodoo-odoo-ee:19.0
rm -rf .odoo-enterprise
# Optional and broader: removes unrelated unused build cache too.
docker builder prune
```

Temporary build contexts are removed on success, failure, and interruption. The supported stable matrix is currently Odoo 17–19. There is no official `odoo:20.0` image yet, so Odoo 20 is not included.

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
