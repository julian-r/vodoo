# Generic CRUD

`GenericNamespace` for generic model operations that work with any Odoo model, accessed as `client.generic`.

`update(..., check_write_date=expected)` offers a **best-effort, non-atomic**
freshness preflight, not compare-and-set. Changes after the read or within the
same second can be missed. See [freshness checks and errors](../guide/library.md#best-effort-freshness-checks).

::: vodoo.generic
    options:
      show_source: true
      members_order: source
