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
| `messages` | Chatter records, ordered by ascending ID, with raw HTML bodies, author, date, subject/type/subtype, email source, attachment IDs and tracking-value IDs. |
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

::: vodoo.project_tasks
    options:
      show_source: true
      members_order: source
