# Project Tasks

`TaskNamespace` for the `project.task` model, accessed as `client.tasks`.

## Description files in the CLI

Use a UTF-8 file or stdin instead of shell-escaped multiline arguments:

```bash
vodoo project-task set 42 --description-file task.md
cat task.md | vodoo project-task set 42 --description-file -
```

Files are loaded verbatim, including whitespace and line endings, before client
construction. Missing/unreadable files, invalid UTF-8, and combining a file with
an inline `description=...` assignment fail before mutation. The content uses the
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
