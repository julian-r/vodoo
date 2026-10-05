"""Read-only task context assembly, shared by sync and async namespaces.

The request plan keeps section/error/pagination semantics identical for both clients.
No CLI dependencies or mutation methods are used here.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from vodoo.exceptions import RecordNotFoundError
from vodoo.urls import build_record_url

if TYPE_CHECKING:
    from vodoo.aio.client import AsyncOdooClient
    from vodoo.client import OdooClient

# Provisional resolver seam: replace private resolver calls with
# vodoo.task_relations.resolve_task_relations / async_resolve_task_relations.
_RELATION_MODELS = {
    "stage_id": "project.task.type",
    "project_id": "project.project",
    "tag_ids": "project.tags",
    "user_ids": "res.users",
    "parent_id": "project.task",
    "depend_on_ids": "project.task",
    "dependent_ids": "project.task",
}
CORE_FIELDS = (
    "id",
    "name",
    "description",
    "write_date",
    "create_date",
    "active",
    "priority",
    "state",
    "date_deadline",
    "partner_id",
)
MESSAGE_FIELDS = [
    "id",
    "date",
    "author_id",
    "body",
    "subject",
    "message_type",
    "subtype_id",
    "email_from",
    "attachment_ids",
    "tracking_value_ids",
]
ATTACHMENT_FIELDS = ["id", "name", "file_size", "mimetype", "create_date", "type", "url"]


def _relation_ids(task: dict[str, Any], name: str) -> list[int]:
    value = task[name]
    if value is None or value is False or value == []:
        return []
    if name in {"stage_id", "project_id", "parent_id"}:
        ids = [value[0] if isinstance(value, (list, tuple)) else value]
    elif isinstance(value, (list, tuple)):
        ids = list(value)
    else:
        raise ValueError(f"Malformed relation field: {name}")
    if any(type(record_id) is not int or record_id <= 0 for record_id in ids):
        raise ValueError(f"Malformed relation IDs: {name}")
    return sorted(set(ids))


def _resolved_records(
    model: str, ids: list[int], records: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    by_id = {record["id"]: record for record in records}
    for record_id in ids:
        if record_id not in by_id:
            raise RecordNotFoundError(model, record_id)
    if any(not isinstance(by_id[record_id].get("display_name"), str) for record_id in ids):
        raise ValueError(f"Missing display_name in {model} response")
    return [{"id": record_id, "name": by_id[record_id]["display_name"]} for record_id in ids]


def _resolve_context_relations(
    client: OdooClient,
    task: dict[str, Any],
    *,
    fields_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Private provisional implementation of the #89 resolver contract."""
    result: dict[str, Any] = {}
    for name, model in _RELATION_MODELS.items():
        if name in task:
            if fields_info is not None and name not in fields_info:
                raise ValueError(f"Unsupported relation: {name}")
            ids = _relation_ids(task, name)
            records = client.read(model, ids, fields=["display_name"]) if ids else []
            result[name] = _resolved_records(model, ids, records)
    return result


async def _async_resolve_context_relations(
    client: AsyncOdooClient,
    task: dict[str, Any],
    *,
    fields_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Private provisional implementation of the async #89 resolver contract."""
    result: dict[str, Any] = {}
    for name, model in _RELATION_MODELS.items():
        if name in task:
            if fields_info is not None and name not in fields_info:
                raise ValueError(f"Unsupported relation: {name}")
            ids = _relation_ids(task, name)
            records = await client.read(model, ids, fields=["display_name"]) if ids else []
            result[name] = _resolved_records(model, ids, records)
    return result


@dataclass
class _Request:
    method: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


def _error(result: dict[str, Any], section: str, exc: Exception, **metadata: Any) -> None:
    result["errors"].append(
        {
            "section": section,
            "type": type(exc).__name__,
            "message": str(exc),
            **metadata,
        }
    )


def _unsupported(result: dict[str, Any], section: str, names: list[str]) -> None:
    if names:
        result["errors"].append(
            {
                "section": section,
                "type": "unsupported_fields",
                "message": "Fields unavailable on this server or to this user",
                "fields": names,
            }
        )


def _check_relation_fields(
    result: dict[str, Any],
    task: dict[str, Any],
    definitions: dict[str, Any] | None,
) -> None:
    missing = [name for name in _RELATION_MODELS if name not in task]
    unsupported = [name for name in missing if definitions is not None and name not in definitions]
    _unsupported(result, "relations", unsupported)
    missing = [name for name in missing if name not in unsupported]
    if missing:
        _error(
            result,
            "relations",
            ValueError("Relation fields missing from task response"),
            fields=missing,
        )


def _pages(
    result: dict[str, Any],
    section: str,
    model: str,
    domain: list[Any],
    fields: list[str],
    page_size: int,
    max_pages: int | None,
) -> Generator[_Request, Any, None]:
    after_id = 0
    pages = 0
    status: dict[str, Any] = {"complete": False, "count": 0, "continuation": None}
    result["pagination"][section] = status
    while True:
        next_domain = [*domain, ("id", ">", after_id)]
        continuation = {
            "model": model,
            "domain": next_domain,
            "fields": fields,
            "order": "id asc",
            "after_id": after_id,
            "page_size": page_size,
        }
        status["continuation"] = continuation
        # One-row lookahead establishes whether a page cap actually truncated data.
        capped = max_pages is not None and pages >= max_pages
        try:
            records = yield _Request(
                "search_read",
                (model,),
                {
                    "domain": next_domain,
                    "fields": fields,
                    "order": "id asc",
                    "limit": 1 if capped else page_size,
                },
            )
            if not records:
                status.update(complete=True, continuation=None)
                return
            ids = [record["id"] for record in records]
            if ids != sorted(set(ids)) or ids[0] <= after_id:
                raise ValueError("Non-advancing or unordered pagination response")
        except Exception as exc:
            _error(result, section, exc)
            return
        if capped:
            return
        result[section].extend(records)
        status["count"] = len(result[section])
        after_id = ids[-1]
        pages += 1


def _context_plan(
    task_id: int,
    fields: list[str] | None,
    page_size: int,
    max_pages: int | None,
) -> Generator[_Request, Any, dict[str, Any]]:
    if page_size < 1 or (max_pages is not None and max_pages < 1):
        raise ValueError("page_size and max_pages must be positive")
    result: dict[str, Any] = {
        "schema_version": 1,
        "task": None,
        "relations": {},
        "messages": [],
        "attachments": [],
        "url": None,
        "write_date": None,
        "pagination": {},
        "errors": [],
        "complete": False,
    }
    requested = list(dict.fromkeys([*CORE_FIELDS, *(fields or []), *_RELATION_MODELS]))
    selected = requested
    definitions: dict[str, Any] | None = None
    try:
        definitions = yield _Request("fields_get", ("project.task",), {"attributes": ["type"]})
        selected = [name for name in requested if name in definitions]
        _unsupported(result, "task", [name for name in requested if name not in definitions])
    except Exception as exc:
        _error(result, "task", exc, operation="fields_get")
    task = None
    try:
        records = yield _Request("read", ("project.task", [task_id]), {"fields": selected})
        if not records:
            raise RecordNotFoundError("project.task", task_id)
        task = records[0]
        result["task"] = task
        result["write_date"] = task.get("write_date")
        # Missing values are not interpreted as empty relations.
        missing = [name for name in selected if name not in task]
        if missing:
            _error(
                result,
                "task",
                ValueError("Requested fields missing from read response"),
                fields=missing,
            )
    except RecordNotFoundError:
        raise
    except Exception as exc:
        _error(result, "task", exc, operation="read")
    if task is not None:
        _check_relation_fields(result, task, definitions)
        try:
            result["relations"] = yield _Request("relations", (task,), {"fields_info": definitions})
        except Exception as exc:
            _error(result, "relations", exc)
    else:
        _error(result, "relations", ValueError("Task read failed; relations unavailable"))
    yield from _pages(
        result,
        "messages",
        "mail.message",
        [("model", "=", "project.task"), ("res_id", "=", task_id)],
        MESSAGE_FIELDS,
        page_size,
        max_pages,
    )
    attachment_domain: list[Any] = [("res_model", "=", "project.task"), ("res_id", "=", task_id)]
    message_attachment_ids = sorted(
        {
            attachment_id
            for message in result["messages"]
            for attachment_id in (message.get("attachment_ids") or [])
        }
    )
    if message_attachment_ids:
        attachment_domain = ["|", "&", *attachment_domain, ("id", "in", message_attachment_ids)]
    yield from _pages(
        result,
        "attachments",
        "ir.attachment",
        attachment_domain,
        ATTACHMENT_FIELDS,
        page_size,
        max_pages,
    )
    try:
        result["url"] = yield _Request("url", (task_id,))
    except Exception as exc:
        _error(result, "url", exc)
    result["complete"] = not result["errors"] and all(
        status["complete"] for status in result["pagination"].values()
    )
    return result


def _url(client: OdooClient | AsyncOdooClient, task_id: int) -> str:
    return build_record_url(
        client.config.url,
        "project.task",
        task_id,
        "json2" if client.is_json2 else "jsonrpc",
    )


def get_task_context(
    client: OdooClient,
    task_id: int,
    fields: list[str] | None = None,
    *,
    page_size: int = 100,
    max_pages: int | None = None,
) -> dict[str, Any]:
    """Fetch context; exhaustive by default, with explicit errors and continuation."""
    plan = _context_plan(task_id, fields, page_size, max_pages)
    request = next(plan)
    response: Any
    while True:
        try:
            if request.method == "relations":
                response = _resolve_context_relations(client, *request.args, **request.kwargs)
            elif request.method == "url":
                response = _url(client, *request.args)
            else:
                response = getattr(client, request.method)(*request.args, **request.kwargs)
        except Exception as exc:
            try:
                request = plan.throw(exc)
            except StopIteration as done:
                return dict(done.value)
        else:
            try:
                request = plan.send(response)
            except StopIteration as done:
                return dict(done.value)


async def async_get_task_context(
    client: AsyncOdooClient,
    task_id: int,
    fields: list[str] | None = None,
    *,
    page_size: int = 100,
    max_pages: int | None = None,
) -> dict[str, Any]:
    """Async equivalent of :func:`get_task_context` with the same response contract."""
    plan = _context_plan(task_id, fields, page_size, max_pages)
    request = next(plan)
    response: Any
    while True:
        try:
            if request.method == "relations":
                response = await _async_resolve_context_relations(
                    client, *request.args, **request.kwargs
                )
            elif request.method == "url":
                response = _url(client, *request.args)
            else:
                response = await getattr(client, request.method)(*request.args, **request.kwargs)
        except Exception as exc:
            try:
                request = plan.throw(exc)
            except StopIteration as done:
                return dict(done.value)
        else:
            try:
                request = plan.send(response)
            except StopIteration as done:
                return dict(done.value)
