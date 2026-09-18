# Cross-language conformance

`fixtures/v1.json` is the normative, language-neutral contract shared by the Python and TypeScript SDKs. Each implementation is checked independently against the fixture; neither implementation is used as the oracle.

The fixture covers:

- JSON-2 positional-to-named body mapping and response normalization
- JSON-RPC authentication and `execute_kw` envelopes
- canonical request paths, headers, and decoded JSON bodies
- `name_search` result filtering and typed Odoo errors
- UTC date/datetime and base64 vectors

TypeScript date and binary rows exercise production codecs. Python has no standalone public codec API, so its date and binary rows use an explicitly test-local stdlib adapter. Transport and error rows exercise production code in both languages.

Run both consumers:

```bash
uv run pytest tests/conformance -q
pnpm --dir packages/typescript test
```
