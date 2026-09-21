# Cross-language conformance

`fixtures/v1.json` is the normative, language-neutral contract shared by the Python, TypeScript, and Swift SDKs. Each implementation is checked independently against the fixture; no implementation is used as the oracle.

The fixture covers:

- JSON-2 positional-to-named body mapping and response normalization
- JSON-RPC authentication and `execute_kw` envelopes
- canonical request paths, headers, and decoded JSON bodies
- `name_search` result filtering and typed Odoo errors
- every ORM/x2many command and retry-policy decision
- client-level false/null normalization and create-result validation
- recording-client operation payloads for generated/simple namespaces
- UTC date/datetime and base64 vectors

TypeScript date and binary rows exercise production codecs. Swift consumes the command, JSON-2 body, legacy envelope, retry, name-search, date, create-result, operation, and generated-metadata vectors through XCTest. Its feature-parity XCTest suite separately covers every namespace workflow, including messaging, attachments, CRM aggregation, documents, security, and timers. Python has no standalone public codec API, so its date and binary rows use an explicitly test-local stdlib adapter. Transport and error rows exercise production code in Python and TypeScript.

Run both consumers:

```bash
uv run pytest tests/conformance -q
pnpm --dir packages/typescript test
swift test
```
