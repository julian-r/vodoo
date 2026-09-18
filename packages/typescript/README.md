# vodoo for TypeScript

Dependency-free ESM client for Odoo's legacy JSON-RPC API (17–18) and JSON-2 API (19+). It uses the standard `fetch` API and is designed to run in Cloudflare Workers without Node.js compatibility flags.

> Initial slice: generic client operations and the `project.project` namespace. Common namespace support currently includes `list`, `get`, `set`, `fields`, and `url`; messaging and attachment helpers will follow in later slices.

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

Project and milestone date fields exposed by the typed namespace are JavaScript `Date` values interpreted in UTC. Generic model operations preserve raw Odoo wire values because arbitrary model field types are not known.

## Development

The source manifest is intentionally marked private and has no hard-coded version. Release automation will stage a publishable manifest using the repository's git-tag version.

```bash
uv run python -m tools.codegen check
pnpm --dir packages/typescript typecheck
pnpm --dir packages/typescript test
pnpm --dir packages/typescript build
```

The live transport/project suite runs against the Community Odoo 17–19 Docker matrix used by the Python client. The `project` module, including `project.milestone`, is provided by the Community source tree; enterprise-only namespaces remain separate conditional slices.

```bash
# After provisioning an integration instance:
set -a
source tests/integration/.env.test.19
set +a
pnpm --dir packages/typescript typecheck:integration
pnpm --dir packages/typescript test:integration
```
