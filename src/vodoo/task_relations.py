"""Read-only task relation resolution shared by sync/async consumers.

``resolve_task_relations(client, task, *, fields_info=None)`` and
``await async_resolve_task_relations(client, task, *, fields_info=None)`` return
``dict[str, list[ResolvedRelation]]`` without changing ``task``. Clients need
only a compatible ``read(model, ids, fields=None)`` method. Optional task field
metadata distinguishes unsupported server fields from empty relations.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol, TypedDict

from vodoo.exceptions import RecordNotFoundError, RecordOperationError


class ResolvedRelation(TypedDict):
    """Stable relation ID and Odoo display name."""

    id: int
    name: str


class TaskRelationError(RecordOperationError):
    """Malformed task relation or related record response."""


class UnsupportedTaskRelationError(TaskRelationError):
    """A supplied task relation is absent from supplied server field metadata."""


class RelationReader(Protocol):
    """Minimal synchronous client interface for relation lookup."""

    def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]: ...


class AsyncRelationReader(Protocol):
    """Minimal asynchronous client interface for relation lookup."""

    async def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]: ...


# Field order is stable. Reverse dependencies use Odoo's actual dependent_ids.
_RELATIONS: dict[str, tuple[str, bool]] = {
    "tag_ids": ("project.tags", False),
    "user_ids": ("res.users", False),
    "project_id": ("project.project", True),
    "stage_id": ("project.task.type", True),
    "parent_id": ("project.task", True),
    "depend_on_ids": ("project.task", False),
    "dependent_ids": ("project.task", False),
}


def _valid_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _relation_ids(field: str, value: Any, many2one: bool) -> list[int]:
    if value is None or value is False:
        return []
    if isinstance(value, (list, tuple)) and not value:
        return []
    if many2one:
        if _valid_id(value):
            return [value]
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and _valid_id(value[0])
            and isinstance(value[1], str)
        ):
            return [value[0]]
    elif isinstance(value, (list, tuple)) and all(_valid_id(item) for item in value):
        return sorted(set(value))
    raise TaskRelationError(f"Malformed task relation {field}: {value!r}")


def _plan(
    task: Mapping[str, Any], fields_info: Mapping[str, Any] | None
) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    relations: dict[str, list[int]] = {}
    batches: dict[str, set[int]] = {}
    for field, (model, many2one) in _RELATIONS.items():
        if field not in task:
            continue
        if fields_info is not None and field not in fields_info:
            raise UnsupportedTaskRelationError(
                f"Task relation {field} is unsupported by this server"
            )
        ids = _relation_ids(field, task[field], many2one)
        relations[field] = ids
        if ids:
            batches.setdefault(model, set()).update(ids)
    return relations, {model: sorted(ids) for model, ids in batches.items()}


def _names(model: str, ids: list[int], records: list[dict[str, Any]]) -> dict[int, str]:
    names: dict[int, str] = {}
    for record in records:
        record_id = record.get("id")
        name = record.get("display_name")
        if not _valid_id(record_id) or record_id not in ids or record_id in names:
            raise TaskRelationError(f"Invalid relation lookup ID in {model}: {record_id!r}")
        if not isinstance(name, str):
            raise TaskRelationError(
                f"Missing or invalid display_name for {model} record {record_id}"
            )
        names[record_id] = name
    for record_id in ids:
        if record_id not in names:
            raise RecordNotFoundError(model, record_id)
    return names


def _assemble(
    relations: dict[str, list[int]], names: dict[str, dict[int, str]]
) -> dict[str, list[ResolvedRelation]]:
    return {
        field: [
            {"id": record_id, "name": names[_RELATIONS[field][0]][record_id]} for record_id in ids
        ]
        for field, ids in relations.items()
    }


def resolve_task_relations(
    client: RelationReader,
    task: Mapping[str, Any],
    *,
    fields_info: Mapping[str, Any] | None = None,
) -> dict[str, list[ResolvedRelation]]:
    """Resolve supplied task fields, batching one read per related model.

    Values are lists even for many2one, unique and sorted by numeric ID. Present
    empty fields resolve to []; absent fields are omitted (not assumed empty).
    Raw fields are untouched. Names always come from Odoo ``display_name``.
    Malformed values/responses raise TaskRelationError; supplied fields absent
    from optional metadata raise UnsupportedTaskRelationError. Missing records
    raise RecordNotFoundError; access/transport failures propagate unchanged.
    """
    relations, batches = _plan(task, fields_info)
    names = {
        model: _names(model, ids, client.read(model, ids, fields=["id", "display_name"]))
        for model, ids in batches.items()
    }
    return _assemble(relations, names)


async def async_resolve_task_relations(
    client: AsyncRelationReader,
    task: Mapping[str, Any],
    *,
    fields_info: Mapping[str, Any] | None = None,
) -> dict[str, list[ResolvedRelation]]:
    """Async counterpart of resolve_task_relations, with identical schema/errors."""
    relations, batches = _plan(task, fields_info)
    names: dict[str, dict[int, str]] = {}
    for model, ids in batches.items():
        names[model] = _names(
            model, ids, await client.read(model, ids, fields=["id", "display_name"])
        )
    return _assemble(relations, names)
