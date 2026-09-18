# vodoo for TypeScript

Dependency-free ESM client for Odoo's legacy JSON-RPC API (17–18) and JSON-2 API (19+). It uses the standard `fetch` API and is designed to run in Cloudflare Workers without Node.js compatibility flags.

Typed namespaces are available for projects, tasks, CRM, helpdesk, knowledge, documents, activities, account moves, timers, and security, plus an arbitrary-model `generic` namespace. Shared namespace support includes CRUD, chatter messages, tags, and in-memory attachments.

## Cloudflare Worker

```ts
import { OdooClient } from "vodoo";

interface Env {
  ODOO_URL: string;
  ODOO_DATABASE: string;
  ODOO_USERNAME: string;
  ODOO_PASSWORD: string;
}

export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    const client = new OdooClient({
      url: env.ODOO_URL,
      database: env.ODOO_DATABASE,
      username: env.ODOO_USERNAME,
      password: env.ODOO_PASSWORD,
    });

    const projects = await client.projects.list({ limit: 10 });
    const milestones = await client.projects.milestones(7);
    const milestoneId = await client.projects.createMilestone(
      7,
      "Launch",
      new Date("2026-12-01T00:00:00Z"),
    );

    return Response.json({ projects, milestones, milestoneId });
  },
};
```

Credentials belong in Worker secret bindings, never in source or `wrangler.jsonc`.

## Transport behavior

The client lazily tries Odoo 19 JSON-2 authentication and falls back to legacy JSON-RPC under the same conditions as the Python async client. It uses a 30-second timeout and retries only idempotent read operations after network failures (two retries with exponential backoff by default). Provide `autoDetect: false` to force legacy JSON-RPC or inject a transport for tests.

Known date and datetime fields exposed by typed namespaces are JavaScript `Date` values interpreted in UTC. Generic model operations preserve raw Odoo wire values because arbitrary model field types are not known.

Markdown passed through namespace helpers or the exported `Markdown` wrapper is rendered by a dependency-free safe subset: raw markup is escaped and links are limited to safe protocols. Use the exported `HTML` wrapper only for explicitly trusted raw HTML. `create` and `write` process these wrappers at the top level, matching Python's content-wrapper behavior.

Filesystem paths are intentionally absent from the Worker API. `attach` and `documents.upload` accept `Uint8Array`, `ArrayBuffer`, or `Blob`; attachment helpers and `documents.downloadFile` return bytes in memory. Persisting those bytes is the caller's runtime-specific responsibility. Document filenames are sanitized but no directory is created or written.

The documents namespace probes the running server's legacy `documents.folder` versus modern folder-record schema. The timer namespace similarly selects legacy `timer.timer` behavior or Odoo 19 analytic-line timers and handles stop-confirmation wizards. Security password generation uses the Web Crypto API. These paths use only Worker-native globals (`fetch`, `Blob`, `Uint8Array`, `atob`/`btoa`, and `crypto`) and do not import Node runtime modules.

`url(recordId)` remains synchronous and builds the standard Odoo form URL. Knowledge articles additionally expose `resolveUrl(recordId)` for the asynchronous `article_url` lookup with standard-URL fallback.

## Development

The source manifest is intentionally marked private and has no hard-coded version. Release automation will stage a publishable manifest using the repository's git-tag version.

```bash
uv run python -m tools.codegen check
pnpm --dir packages/typescript typecheck
pnpm --dir packages/typescript test
pnpm --dir packages/typescript build
```

The live suite runs transport, project, task, CRM, activity, security, shared-binary, and account-move checks against the Community Odoo 17–19 Docker matrix used by the Python client. Helpdesk, knowledge, documents, and timer checks are enabled only when `ODOO_ENTERPRISE=1`. GitHub CI cannot run those proprietary addons, so Enterprise compatibility remains an explicitly separate integration gate.

```bash
# After provisioning an integration instance:
set -a
source tests/integration/.env.test.19
set +a
pnpm --dir packages/typescript typecheck:integration
pnpm --dir packages/typescript test:integration
```
