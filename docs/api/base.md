# Base Operations

Shared CRUD, messaging, attachment, and display helpers. The `DomainNamespace` base class provides common methods inherited by all domain namespace classes.

Bulk attachment reads and downloads propagate access, transport, decode, and
filesystem failures rather than returning silently partial results. CLI
`download-all` exits nonzero on failure and does not report `ok: true`. Files
already written before an error remain on disk; downloads are not atomic.
Extension filters are applied to metadata before reading attachment content,
including in the TypeScript and Swift SDKs.

::: vodoo.base
    options:
      show_source: true
      members_order: source
      filters:
        - "!^_"
        - "!^configure_output"
