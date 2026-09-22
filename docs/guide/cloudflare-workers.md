# Cloudflare Workers

The TypeScript SDK uses Web Standard APIs and runs in Cloudflare Workers without the `nodejs_compat` flag.

## Configure bindings

Keep non-sensitive Odoo settings in your Worker's `wrangler.jsonc`:

```jsonc
{
  "vars": {
    "ODOO_URL": "https://my-instance.odoo.com",
    "ODOO_DATABASE": "production",
    "ODOO_USERNAME": "worker@example.com"
  }
}
```

Add passwords, API keys, and Cloudflare Access credentials as encrypted Worker secrets. Never commit them to source or Wrangler configuration.

```bash
npx wrangler secret put ODOO_PASSWORD
npx wrangler secret put CF_ACCESS_CLIENT_ID
npx wrangler secret put CF_ACCESS_CLIENT_SECRET
npx wrangler types
```

Run `wrangler types` again whenever bindings change. Vodoo's `OdooWorkerBindings` type is a minimum structural contract, not a replacement for the complete `Env` generated from your Worker configuration. Wrangler environments do not inherit vars or secrets, so configure each environment separately.

## Create the client

```typescript
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
    return Response.json({ projects });
  },
};
```

The factory maps `ODOO_URL`, `ODOO_DATABASE`, `ODOO_USERNAME`, and `ODOO_PASSWORD`. It rejects a missing or empty required binding before making a request. Other application bindings remain owned by the Worker.

Choose a protocol based on the deployed Odoo version:

- `"auto"` (default) probes JSON-2 and falls back to legacy JSON-RPC.
- `"json2"` targets Odoo 19 and sends the requested method directly without a detection request.
- `"jsonrpc"` targets Odoo 17–18.

Custom `headers` are sent on every request in every protocol mode. This supports Cloudflare Access service-token headers without requiring consumers to instantiate transport classes.
