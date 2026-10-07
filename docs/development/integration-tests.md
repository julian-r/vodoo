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

### Native Swift coverage

XCTest runs the portable feature-parity suite plus live Community namespace workflows on Odoo 17–19. Enterprise CI additionally exercises Helpdesk, Knowledge, Documents, and timers. Swift coverage excludes generated sources and enforces lines, functions, and regions independently.

### Cross-language conformance

Python, TypeScript, and Swift independently consume `conformance/fixtures/v1.json`. The hermetic conformance suites verify canonical JSON-RPC and JSON-2 requests, response normalization, and typed error mapping without treating any implementation as the oracle. Date and binary rows are neutral cross-runtime vectors; Python uses an explicitly test-local stdlib adapter because it has no standalone public codec API.

```bash
uv run pytest tests/conformance -q
pnpm --dir packages/typescript test
swift test --enable-code-coverage
```

## Architecture

```
tests/integration/
├── run.sh                  # End-to-end orchestrator
├── setup_odoo.py           # DB provisioning + API key creation
├── conftest.py             # pytest fixtures and markers
├── test_suite.py           # Synchronous Python live scenarios
├── test_async_suite.py     # Async Python live scenarios
├── test_field_access.py    # Share/API-account sync, async, CLI and registry audit
├── service_account.py     # Least-privilege provisioning and inherited-field audit
├── docker-compose.yml      # Parameterized compose file
├── Dockerfile.enterprise   # Builds a local image from validated Enterprise source
├── fetch_enterprise.py     # Secure official-download client and archive validator
├── odoo.conf               # Community Odoo config
└── odoo-enterprise.conf    # Enterprise Odoo config (with addons_path)

packages/typescript/test/integration/
└── odoo.integration.ts     # Native Vitest live scenarios

swift-tests/VodooTests/
├── FeatureParityTests.swift # Hermetic namespace workflow coverage
└── LiveIntegrationTests.swift # Community and Enterprise live scenarios

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

## Least-privilege context and field audit

`setup_odoo.py` provisions a **separate share/API service account** alongside the
admin fixture. It replaces the account's groups with Vodoo's `API Base` and
`API Project` groups (plus `API Knowledge`/`API Helpdesk` in Enterprise). No
`base.group_user`, `base.group_system`, or `base.group_erp_manager` is granted;
the effective group audit verifies this even in reused databases. Existing
admin-backed CRUD suites keep their admin client.

`test_field_access.py` runs on Community and Enterprise 17–19 through both the
local runner and CI. It reproduces the rejected raw tracking read, then verifies
sync/async context and CLI behavior: readable comments and empty-body messages,
attachment references including a chatter-only attachment, exhausted pagination,
explicit unavailable tracking, `complete=false`, and CLI exit status 1. Test
records are seeded and cleaned up by the admin **only in disposable test databases**.
The two attachment fixtures are public so attachment record rules do not confound
this field-access regression; production record rules are never relaxed.

Provisioning also inspects the **loaded Odoo registry** with the service user.
This audits effective `_fields` declarations, including installed inherited
Enterprise overrides, rather than assuming that Community declarations apply.
The metadata-only `.env.test.<suffix>.audit.json` report records:

- Odoo version, immutable image ID, and Enterprise source provenance labels;
- model installation and model read ACL status, separately from field access;
- the explicit task, message, attachment, relation-name, Knowledge, Helpdesk, and
  Documents default projections;
- missing/inaccessible requested fields and all effective group-restricted fields;
- `system_admin_only` for exactly `base.group_system`, `administrative_access`
  for expressions mentioning `base.group_erp_manager`, and `other_field_groups`
  for internal-user, feature, accounting, or other restrictions.

These classifications describe declarations; metadata availability reflects the
actual user's groups. A model ACL denial is **not** evidence of an admin-only
field. No Documents API group is invented merely to make an audit pass. Reports
contain no records, API keys, or proprietary source. CI uploads only the exact
`.audit.json` file, never the credential-bearing env files.

Community validation on Odoo 17.0-20260908, 18.0-20260926, and 19.0-20260926 found
`tracking_value_ids` to be the only unavailable field intersecting the explicit
context/relation projections. Attachment `access_token` is internal-user-only
and not requested; other mail administrative fields are likewise not requested.
This is **not** an exhaustive audit of custom addons, computed-field permissions,
record rules, or arbitrary user-selected fields.

Enterprise Knowledge/Helpdesk/Documents and their inherited fields are audited
when licensed sources are installed. Without those sources the report marks
these models uninstalled; that is not an Enterprise validation result. The
protected Enterprise CI job runs after pushes to `main`, not on fork PRs. Obtain
authorized sources via the workflow above to validate before merge. Future
composite contexts must negotiate projections and explicitly report unavailable
coverage rather than changing rights or fabricating empty values.

Run just this coverage against an already provisioned test database:

```bash
VODOO_TEST_ENV=tests/integration/.env.test.19 \
uv run pytest tests/integration/test_field_access.py --odoo-version 19 -v
```

## API Key Creation

Initial API keys cannot be created remotely: Odoo's `@check_identity` wizard blocks JSON-RPC automation, JSON-2 already requires a key, and private `_generate()` calls are not remotely callable. Instead, `setup_odoo.py` runs `odoo shell` inside the Docker container and calls `_generate()` directly. Key differences by version:

- **Odoo 17**: `_generate(scope, name)` — 2 args
- **Odoo 18+**: `_generate(scope, name, expiration_date)` — 3 args
- **Odoo 19**: expiration is additionally bounded by the user's groups through `api_key_duration`; zero-valued groups default to one day

The test key is bound to the admin user (not `__system__`) through `with_user(admin).sudo()`. For a service account, the same ordering is important: `with_user(service_user)` selects the key owner and `sudo()` authorizes a reviewed lifetime beyond the group default. Production scripts must capture the returned plaintext key directly into a secrets manager instead of printing it in logs.

## Environment Files

Each test run creates a private `.env.test.<suffix>` admin file and a separate
`.env.test.<suffix>.service` credential file, both mode `0600` and Git-ignored.
The metadata-only `.env.test.<suffix>.audit.json` is also Git-ignored. Keys are
not printed. The admin file contains:

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
