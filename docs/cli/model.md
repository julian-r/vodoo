# vodoo model

Generic CRUD operations for any Odoo model. Useful for ad-hoc queries and models not covered by the domain-specific commands.

## Commands

### read

Read records matching a domain filter.

```bash
# Read partners by email domain
vodoo model read res.partner \
    --domain='[["email","ilike","@acme.com"]]' \
    --field name --field email

# Read with limit
vodoo model read res.partner \
    --domain='[["is_company","=",true]]' \
    --field name --limit 10
```

**Options:**

| Option | Description |
|--------|-------------|
| `--domain` | JSON domain filter (Odoo domain syntax) |
| `--field` | Field to include (repeatable) |
| `--limit` | Maximum records |
| `--simple` | Plain TSV output |

### create

Create a new record.

```bash
vodoo model create res.partner name="Acme Corp" email=info@acme.com is_company=true
```

Fields are specified as `key=value` pairs. Values are auto-parsed:

- Integers: `priority=2`
- Booleans: `active=true`, `is_company=false`
- Strings: `name="Acme Corp"` or `name=Acme`

### update

Update an existing record.

```bash
vodoo model update res.partner 123 phone="+1-555-0123" website="https://acme.com"
```

### delete

Delete a record (requires confirmation).

```bash
vodoo model delete res.partner 123 --confirm
```

!!! warning
    Deletion is permanent. Always use `--confirm` to acknowledge.

### call

Call a custom method on a model.

```bash
# Call name_search
vodoo model call res.partner name_search --args='["Acme"]'

# Call with keyword arguments
vodoo model call res.partner name_search --args='["Acme"]' --kwargs='{"limit": 5}'
```

**Options:**

| Option | Description |
|--------|-------------|
| `--args` | JSON-encoded positional arguments |
| `--kwargs` | JSON-encoded keyword arguments |

!!! tip "Safety first"
    Use a [least-privilege service account](../development/security.md) when running generic model operations to prevent accidental data modification.
