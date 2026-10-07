# Project Tasks

`TaskNamespace` for the `project.task` model, accessed as `client.tasks`.

## Read-only context

Use `client.tasks.get(id)` (CLI `project-task show`) for a lightweight single-task
read. Use `client.tasks.context(id)` (CLI `project-task context`) when a decision
requires task fields **plus** relations, chatter, attachments and a canonical URL.
Context never creates, writes, unlinks, posts, or downloads attachment contents.
This increment provides **Python sync/async and CLI only**; TypeScript and Swift
context APIs are not implemented or claimed in the namespace manifest.

```bash
vodoo --json project-task context 807
vodoo --toon project-task context 807 --field planned_date_begin
vodoo --simple project-task context 807 --page-size 50 --max-pages 2
```

```python
context = client.tasks.context(807, fields=["planned_date_begin"])
# Async has the same signature and response:
context = await async_client.tasks.context(807, page_size=50, max_pages=2)
if not context["complete"]:
    # Inspect errors AND pagination before trusting coverage.
    print(context["errors"], context["pagination"])
```

### Stable v1 response

The authoritative JSON Schema is `spec/v1/task-context.schema.json` in the
repository. JSON and TOON serialize the same object. Plain output has one TSV
line per top-level key, with its value JSON-encoded (embedded newlines and tabs
are escaped). Rich output uses literal text, never interpreting task/chatter
content as markup.

| Key | Contract |
| --- | --- |
| `schema_version` | Always `1`. |
| `task` | Raw task fields; `null` if the task read failed. |
| `relations` | Mapping keyed by `stage_id`, `project_id`, `tag_ids`, `user_ids`, `parent_id`, `depend_on_ids` (Blocked By), `dependent_ids` (Block). Each present key contains a list of `{id: int, name: str}` sorted by ID, even for many2one. Empty lists mean no relation; absent keys plus errors mean unavailable coverage. |
| `messages` | Chatter records, ordered by ascending ID, with raw HTML bodies, author, date, subject/type/subtype, email source, attachment IDs and tracking-value IDs when accessible. |
| `attachments` | Metadata (ID, name, size, MIME type, creation date, type and URL) for task-linked attachments and attachments referenced by fetched chatter. No binary contents. |
| `url` | Canonical URL for the selected transport, without an extra version probe; `null` on failure. |
| `write_date` | Task's fetched `write_date`, also preserved in `task`; `null` if unavailable. |
| `pagination` | `messages` and `attachments` each have `complete`, returned `count`, and `continuation` (null when exhausted). |
| `errors` | Explicit section errors with `section`, `type`, `message`, and optional `fields`/`operation`. Empty when no section failed. |
| `complete` | True only when no section errors occurred and both paginated sections were exhausted. |

Default task fields are `id`, `name`, `description`, `write_date`, `create_date`,
`active`, `priority`, `state`, `date_deadline`, `partner_id`, and all seven relation
fields. `--field`/`fields` **adds** requested fields rather than replacing required
context fields. Field metadata is checked first. Missing server fields (including
version/module/access-dependent fields) are explicitly reported as
`unsupported_fields`; missing values in a projected response are a separate
error, not proof that the server lacks the field. No absent reverse dependency
field is interpreted as an empty dependent list.

Task, message, and attachment projections are checked with user-sensitive
`fields_get` metadata for their respective models. Unavailable fields are
omitted from the read and reported as `unsupported_fields` in the corresponding
section. Absence can mean unsupported **or inaccessible**, not just uninstalled. In particular, Odoo restricts `tracking_value_ids` to
administrators: readable chatter (including empty-body change messages) and its
attachment references are still fetched, but `complete` remains false and the
CLI exits with status 1. Message pagination can be exhausted even when field
coverage is incomplete. If message metadata fails, the error is retained and
chatter is attempted without `tracking_value_ids`; completeness remains false.
Other message access failures remain explicit, with no permission escalation.

Accessible tracking-value IDs are **raw references, not resolved old/new values**.
Even `complete=true` means coverage of this v1 projection, not full structured
change history. Context does not read `mail.tracking.value` or invoke chatter
routes that mark messages read/done. Full permission-filtered tracking history
requires a separate read-only API design.

### Least-privilege access and projection policy

Model ACLs authorize operations on a model; they do **not** override field-level
group restrictions. Granting `base.group_system` (Settings/Administrator) or
`base.group_erp_manager` to satisfy a read is not an acceptable workaround.
Context never changes rights or uses elevated access. Record-rule, computed-field,
transport, and business errors remain explicit; metadata is not a guarantee that
a later read will succeed.

The same projection negotiation is used for task, chatter, and attachment fields.
If metadata fails, the original task/attachment projection is attempted and the
error prevents completeness; only the known privileged tracking field is excluded
from the message fallback. Further denied fields can still fail the read rather
than being silently swallowed. At least `id` is always requested, preventing an
empty field list from accidentally requesting every field.

Relation lookups request only `id` and `display_name`; task relation fields are
negotiated first, and failed name lookups remain explicit. Future relation or
Enterprise context sections must negotiate any additional fields and use the same
strict missing-field/error/completeness contract. Enterprise context APIs are not
currently implemented; generic namespace reads do not silently change user-requested
projections or claim this composite context contract.

[Integration coverage](../development/integration-tests.md#least-privilege-context-and-field-audit)
uses provisioned share/API accounts, not just administrators, and distinguishes
model ACL failures from administrative, feature-group, and internal-user field
restrictions. Licensed Enterprise registries are audited separately, including
inherited overrides.

### Completeness, continuation and concurrency

Pagination is exhaustive by default. `page_size` defaults to 100. Reads use
`id asc` and the keyset domain `id > after_id`, continuing until an empty page,
even if the server returns fewer rows than requested. `max_pages` is an optional
positive cap **per section**; a one-row lookahead distinguishes actual truncation
from an exactly exhausted last page. Failed or truncated sections preserve their
fetched records and a continuation containing `model`, `domain`, `fields`,
`order`, `after_id`, and `page_size`. Resume using `client.search_read` with those
values (`limit=page_size`), repeating with the last returned ID to exhaustion.
If chatter is truncated/failed, attachment coverage includes only references
from chatter already fetched; the overall context remains incomplete.

A section failure does not silently remove that section: its stable key remains,
`errors` records the failure, and `complete` is false. **CLI exit status is 1 for
incomplete context**, including truncation, while stdout still contains the
entire JSON/TOON/plain context payload. A missing task raises
`RecordNotFoundError` and uses the existing CLI not-found error contract.

All reads respect the caller's Odoo access rules; complete means exhausted
visible results, not records hidden by record rules. Context is **not an atomic
cross-request snapshot**. Task, relations, chatter and attachments can change
between requests. `write_date` is fetched metadata, not a consistency token or
a guarantee that later reads saw the same state. No mutation is combined with
these reads.

## Description files in the CLI

Use a UTF-8 file or stdin instead of shell-escaped multiline arguments:

```bash
vodoo project-task create --project 2 --name 'Task' --description-file task.md
cat task.md | vodoo project-task create --project 2 --name 'Task' --description-file -
vodoo project-task set 42 --description-file task.md
cat task.md | vodoo project-task set 42 --description-file -
```

Files are loaded verbatim, including whitespace and line endings, before client
construction. Missing/unreadable files, invalid UTF-8, and combining a file with
an inline `--description`/`--desc` value (create) or `description=...` assignment (set)
fail before mutation. The content uses the
existing inline Markdown conversion pipeline; `--no-markdown` disables conversion
and `--html` changes only displayed output. Empty files clear the description.

## Resolved relations

`vodoo --json project-task show 42` (also `--toon`) keeps all raw task fields and
adds `relations`, keyed by original Odoo field names:

```json
{
  "id": 42,
  "tag_ids": [7, 2],
  "project_id": [10, "Website"],
  "relations": {
    "tag_ids": [{"id": 2, "name": "Backend"}, {"id": 7, "name": "Urgent"}],
    "project_id": [{"id": 10, "name": "Website"}]
  }
}
```

Raw ID access is unchanged; no migration is required. Every resolved value is a
list of `{id: int, name: str}`, even for many2one fields. Names are Odoo
`display_name` values; lists deduplicate IDs and sort by **numeric ID**, not name
or lookup response order. Supported relations are `tag_ids`, `user_ids`,
`project_id`, `stage_id`, `parent_id`, `depend_on_ids` (blocking tasks), and
`dependent_ids` (tasks blocked by this task). Present empty relations yield `[]`;
fields absent from the supplied task are omitted, not assumed empty or unsupported.
Default show still reads all fields. `--field` preserves the requested projection
and only resolves relations in that response. Human-readable output is unchanged.

The reusable Python interfaces in `vodoo.task_relations` are:

```python
resolve_task_relations(client, task, *, fields_info=None) -> dict[str, list[ResolvedRelation]]
await async_resolve_task_relations(client, task, *, fields_info=None)
```

The async function has the same return type. Both accept a `Mapping[str, Any]`
task and a sync/async client implementing `read(model, ids, fields=None)`.
Optional `fields_info: Mapping[str, Any]` is task `fields_get` metadata already
available to the caller; the resolver does not fetch metadata itself. Both are
read-only, leave the task untouched, and batch **one read per related model**,
including one shared `project.task` lookup for parent and both dependency fields.
To produce additive library output, use
`{**task, "relations": resolve_task_relations(client, task)}`; async callers await
the corresponding resolver. Namespace `get` remains raw.

Failures are explicit: malformed relation values/lookup responses raise
`TaskRelationError`; a supplied relation missing from supplied field metadata
raises `UnsupportedTaskRelationError` (a `TaskRelationError` subclass). Both derive
from `RecordOperationError`/`VodooError`. Missing related records raise
`RecordNotFoundError`, and access/transport errors propagate unchanged. CLI show
exits with an error rather than returning silently incomplete names. This can
require read access to related models that raw-ID-only output did not require.

::: vodoo.project_tasks
    options:
      show_source: true
      members_order: source
