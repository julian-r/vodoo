# vodoo for TypeScript

Dependency-free ESM client for Odoo's legacy JSON-RPC API (17–18) and JSON-2 API (19+). It uses the standard `fetch` API and is designed to run in Cloudflare Workers without Node.js compatibility flags.

Typed namespaces are available for projects, tasks, CRM, helpdesk, knowledge, documents, activities, account moves, timers, and security, plus an arbitrary-model `generic` namespace. Shared namespace support includes CRUD, chatter messages, tags, and in-memory attachments.

## Cloudflare Worker

`OdooClient.fromBindings` accepts any generated Worker `Env` with the four standard Vodoo bindings. `OdooWorkerBindings` is only the minimum structural contract; keep the complete `Env` definition owned by your Worker and regenerate it with `wrangler types`.

```ts
import { OdooClient } from "vodoo";

export default {
  async fetch(_request: Request, env: Env): Promise<Response> {
    const client = OdooClient.fromBindings(env, {
      protocol: "json2",
      headers: {
        "CF-Access-Client-Id": env.CF_ACCESS_CLIENT_ID,
        "CF-Access-Client-Secret": env.CF_ACCESS_CLIENT_SECRET,
      },
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

Store non-sensitive configuration as Worker vars:

```jsonc
{
  "vars": {
    "ODOO_URL": "https://my-instance.odoo.com",
    "ODOO_DATABASE": "production",
    "ODOO_USERNAME": "worker@example.com",
  },
}
```

Store passwords, API keys, and Cloudflare Access credentials as secrets, never in source or `wrangler.jsonc`:

```bash
npx wrangler secret put ODOO_PASSWORD
npx wrangler secret put CF_ACCESS_CLIENT_ID
npx wrangler secret put CF_ACCESS_CLIENT_SECRET
npx wrangler types
```

Use separate secrets for each Wrangler environment. Bindings are not inherited between environments.

## Transport behavior

The default `protocol: "auto"` lazily tries Odoo 19 JSON-2 authentication and falls back to legacy JSON-RPC under the same conditions as the Python async client. Use `protocol: "json2"` for Odoo 19 to send the requested operation directly, without a detection/authentication request first. Use `protocol: "jsonrpc"` for Odoo 17–18. Custom `headers` are included on every request for all protocols.

The client uses a 30-second timeout and retries only idempotent read operations after network failures (two retries with exponential backoff by default). The older `autoDetect: false` constructor option remains as a compatibility alias for `protocol: "jsonrpc"`; new code should use `protocol` or `fromBindings`.

Known date and datetime fields exposed by typed namespaces are JavaScript `Date` values interpreted in UTC. Generic model operations preserve raw Odoo wire values because arbitrary model field types are not known.

Markdown passed through namespace helpers or the exported `Markdown` wrapper is rendered by a dependency-free safe subset: raw markup is escaped and links are limited to safe protocols. Use the exported `HTML` wrapper only for explicitly trusted raw HTML. `create` and `write` process these wrappers at the top level, matching Python's content-wrapper behavior.

Filesystem paths are intentionally absent from the Worker API. `attach` and `documents.upload` accept `Uint8Array`, `ArrayBuffer`, or `Blob`; attachment helpers and `documents.downloadFile` return bytes in memory. Persisting those bytes is the caller's runtime-specific responsibility. Document filenames are sanitized but no directory is created or written.

The documents namespace probes the running server's legacy `documents.folder` versus modern folder-record schema. The timer namespace similarly selects legacy `timer.timer` behavior or Odoo 19 analytic-line timers and handles stop-confirmation wizards. Security password generation uses the Web Crypto API. These paths use only Worker-native globals (`fetch`, `Blob`, `Uint8Array`, `atob`/`btoa`, and `crypto`) and do not import Node runtime modules.

`url(recordId)` remains synchronous. It builds the canonical `/odoo/{model}/{id}` form URL when JSON-2 is explicitly selected or has been selected by an earlier operation, and retains the legacy `/web#...` URL for JSON-RPC or an uninitialized auto-detecting client. URL generation never performs a detection request. Knowledge articles additionally expose `resolveUrl(recordId)` for the asynchronous `article_url` lookup with this transport-aware fallback.

## Development

The source manifest is intentionally marked private and has no hard-coded version. `scripts/stage_typescript_package.py` creates a publishable manifest from the repository git-tag version. CI verifies the staged tarball, and the release workflow publishes it to npm alongside PyPI.

```bash
uv run python -m tools.codegen check
pnpm --dir packages/typescript typecheck
pnpm --dir packages/typescript test
pnpm --dir packages/typescript build
```

The native Vitest live suite reports 75 independently named Community scenarios per Odoo version and 107 Enterprise scenarios. It covers transport, projects, tasks, CRM, activities, security, binary data, account moves, errors, helpdesk, knowledge, documents, and timers. Public pull-request CI runs the Community Odoo 17–19 matrix; Enterprise compatibility runs only in the protected, main-branch `enterprise-ci` environment.

Python and TypeScript also consume the same normative fixture at `conformance/fixtures/v1.json`. Their hermetic tests independently verify JSON-RPC/JSON-2 request semantics, normalization, and errors. Date and binary rows are neutral cross-runtime vectors; TypeScript runs them through its production codecs, while Python uses a test-local stdlib adapter because it has no standalone codec API.

```bash
# After provisioning an integration instance:
set -a
source tests/integration/.env.test.19
set +a
pnpm --dir packages/typescript typecheck:integration
pnpm --dir packages/typescript test:integration
```
