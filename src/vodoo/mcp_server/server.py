"""Vodoo MCP server: Odoo tools for Claude Desktop and other MCP clients.

The server speaks MCP over stdio and talks to Odoo through :class:`AsyncOdooClient`,
so it shares Vodoo's configuration, instance profiles, keyring secrets, and the
JSON-2 / legacy JSON-RPC transport auto-detection.

Tool groups:

* **Read** (always on): search/read/count records, field metadata, name search,
  chatter, attachments, accounting moves, timesheets.
* **Write** (``allow_write=True``): create/update records, call model methods,
  post chatter messages, attach files, accounting actions (create, post, reset to
  draft, cancel, register payment), activities, and timers.
* **Delete** (``allow_delete=True``): unlink records.
"""

import asyncio
import functools
import inspect
import json
import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx2 as httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from pydantic import BaseModel, Field

from vodoo.account_moves import build_account_move_domain
from vodoo.aio.auth import message_post_sudo_with_id
from vodoo.aio.client import AsyncOdooClient
from vodoo.base import _html_to_markdown
from vodoo.config import OdooConfig, get_config
from vodoo.content import Markdown
from vodoo.exceptions import VodooError
from vodoo.generated.account_moves import _GeneratedAccountMoveAttrs
from vodoo.generated.activities import _GeneratedActivityAttrs
from vodoo.generated.crm import _GeneratedCRMAttrs
from vodoo.generated.documents import _GeneratedDocumentAttrs
from vodoo.generated.helpdesk import _GeneratedHelpdeskAttrs
from vodoo.generated.knowledge import _GeneratedKnowledgeAttrs
from vodoo.generated.project_tasks import _GeneratedTaskAttrs
from vodoo.generated.projects import _GeneratedProjectAttrs
from vodoo.timer import Timesheet
from vodoo.urls import build_record_url

SERVER_NAME = "vodoo"
MAX_LIMIT = 500
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "vodoo"
DEFAULT_UPLOAD_DIRS = (
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Documents",
)

logger = logging.getLogger(__name__)

# Models with curated default field lists (from the spec-generated namespaces).
_KNOWN_MODELS: dict[str, tuple[list[str], list[str] | None]] = {
    attrs._model: (list(attrs._default_fields), attrs._default_detail_fields)
    for attrs in (
        _GeneratedAccountMoveAttrs,
        _GeneratedActivityAttrs,
        _GeneratedCRMAttrs,
        _GeneratedDocumentAttrs,
        _GeneratedHelpdeskAttrs,
        _GeneratedKnowledgeAttrs,
        _GeneratedTaskAttrs,
        _GeneratedProjectAttrs,
    )
}

_FIELD_ATTRIBUTES = ["string", "type", "required", "readonly", "relation", "selection"]
_HTML_KEYS = {"body", "description", "narration", "note"}
_HTML_TAG = re.compile(r"<[a-zA-Z/][^>]*>")

_MOVE_LINE_FIELDS = [
    "id",
    "display_type",
    "name",
    "product_id",
    "account_id",
    "partner_id",
    "quantity",
    "price_unit",
    "discount",
    "tax_ids",
    "price_subtotal",
    "price_total",
    "debit",
    "credit",
]
_MOVE_SUMMARY_FIELDS = [
    "id",
    "name",
    "move_type",
    "state",
    "payment_state",
    "partner_id",
    "invoice_date",
    "invoice_date_due",
    "amount_total",
    "amount_residual",
    "currency_id",
]

INSTRUCTIONS = """\
Tools for one Odoo instance (via Vodoo).

Conventions:
- Domains use Odoo syntax: [["state", "=", "posted"], ["partner_id.name", "ilike", "acme"]].
  Use "|" / "&" / "!" prefix operators for OR / AND / NOT.
- Many2one values are returned as [id, "Display Name"]; write them as a plain id.
- x2many writes use Odoo command lists, e.g. {"tag_ids": [[6, 0, [1, 2]]]} (replace),
  [[0, 0, {...}]] (create line), [[1, id, {...}]] (update line), [[3, id, 0]] (unlink).
  The delete command [[2, id, 0]] needs delete mode.
- Unknown field names? Call get_fields first. Unknown record id? Use name_search.
- Dates are "YYYY-MM-DD"; datetimes are UTC "YYYY-MM-DD HH:MM:SS".

Accounting (account.move): list_account_moves / get_account_move to inspect;
create_account_move creates drafts; post_account_moves validates them;
register_payment pays posted invoices/bills. Posting assigns a sequence number and is
hard to undo; confirm with the user before posting, cancelling, or paying.
"""


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class MoveLine(BaseModel):
    """One line of an invoice, bill, or journal entry."""

    name: str | None = Field(default=None, description="Line label/description.")
    product_id: int | None = Field(default=None, description="product.product id.")
    account_id: int | None = Field(
        default=None,
        description="account.account id. Required for journal entries; "
        "optional for invoices (defaults from product/journal).",
    )
    quantity: float | None = Field(default=None, description="Quantity (invoice lines).")
    price_unit: float | None = Field(default=None, description="Unit price (invoice lines).")
    discount: float | None = Field(default=None, description="Discount in percent.")
    tax_ids: list[int] | None = Field(
        default=None,
        description="account.tax ids. Omit to use defaults; [] for no taxes.",
    )
    debit: float | None = Field(default=None, description="Debit (journal entries only).")
    credit: float | None = Field(default=None, description="Credit (journal entries only).")
    partner_id: int | None = Field(default=None, description="Partner (journal entries).")
    extra: dict[str, Any] | None = Field(
        default=None,
        description="Any other account.move.line field values.",
    )

    def to_values(self) -> dict[str, Any]:
        """Convert to account.move.line create values."""
        values = self.model_dump(exclude_none=True, exclude={"extra", "tax_ids"})
        if self.tax_ids is not None:
            values["tax_ids"] = [(6, 0, self.tax_ids)]
        if self.extra:
            values.update(self.extra)
        return values


MoveType = Literal["out_invoice", "out_refund", "in_invoice", "in_refund", "entry"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _secret_variants(values: list[str]) -> list[str]:
    """All spellings of secrets that can appear in an error message."""
    variants: set[str] = set()
    for value in values:
        candidates = [value, value.strip(), repr(value)[1:-1], repr(value.strip())[1:-1]]
        # Header values such as "Bearer <token>": also redact the token alone.
        candidates += [part for part in value.split() if len(part) >= 8]
        # Every length counts: a short password is still a password.
        variants.update(c for c in candidates if c)
    return sorted(variants, key=len, reverse=True)


def _redact(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        text = text.replace(secret, "[redacted]")
    return text


def _error_message(exc: Exception) -> str:
    """Message for the model. Only expected error types keep their details."""
    if isinstance(exc, ToolError):
        return str(exc)
    if isinstance(exc, VodooError | ValueError | LookupError | OSError):
        return f"{type(exc).__name__}: {str(exc) or type(exc).__name__}"
    if isinstance(exc, httpx.HTTPError):
        return f"Network error talking to Odoo ({type(exc).__name__}). Check ODOO_URL."
    return f"Unexpected error ({type(exc).__name__}). See the MCP server log."


def _as_tool[**P](
    fn: Callable[P, Awaitable[Any]], secrets: Callable[[], list[str]]
) -> Callable[P, Awaitable[str]]:
    """Serialize results as one JSON text block; report failures as tool errors.

    The SDK would split a returned list into one content block per item (and an
    empty list into no content at all), so results are encoded here instead.
    Error messages are redacted: the SDK returns them to the model and also logs them.
    """

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> str:
        try:
            result = await fn(*args, **kwargs)
        except Exception as exc:
            known = secrets()
            message = _redact(_error_message(exc), known)
            if not isinstance(exc, ToolError | VodooError | ValueError | LookupError | OSError):
                detail = _redact(str(exc), known)
                logger.warning("Tool %s failed: %s: %r", fn.__name__, type(exc).__name__, detail)
            raise ToolError(message) from None
        return json.dumps(result, ensure_ascii=False, default=str)

    return wrapper


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _contains_delete_command(value: Any) -> bool:
    """True if *value* holds an x2many delete command at any depth.

    Odoo compares the command code with ``==``, so ``[2, id]``, ``[2.0, id, 0]`` and
    forms with extra elements all delete. Any list whose first element equals 2 and
    whose second element is a number counts as a delete command.
    """
    if isinstance(value, dict):
        return any(_contains_delete_command(v) for v in value.values())
    if isinstance(value, list | tuple):
        for item in value:
            if isinstance(item, list | tuple) and item and _is_number(item[0]):
                # An x2many command. Only its values dicts can nest more commands;
                # the id list of [6, 0, ids] holds plain ids.
                if item[0] == 2 and len(item) >= 2 and _is_number(item[1]):
                    return True
                if any(isinstance(part, dict) and _contains_delete_command(part) for part in item):
                    return True
            elif _contains_delete_command(item):
                return True
    return False


def _guard_delete(allow_delete: bool, *payloads: Any) -> None:
    """Keep deletion behind --allow-delete, also inside x2many commands."""
    if not allow_delete and any(_contains_delete_command(p) for p in payloads):
        raise ToolError(
            "The x2many command [2, id, 0] deletes records and needs a server started "
            "with --allow-delete. Use [3, id, 0] to unlink without deleting."
        )


class _FilePolicy:
    """Local folders the server may write downloads to or read uploads from."""

    def __init__(self, download_dir: Path, upload_roots: list[Path]) -> None:
        self.download_dir = download_dir.expanduser()
        self.upload_roots = [root.expanduser() for root in upload_roots]

    @staticmethod
    def _inside(path: Path, roots: list[Path]) -> Path | None:
        """Return the resolved *path* if it is inside a root without hidden parts."""
        resolved = path.resolve()
        for root in roots:
            real_root = root.resolve()
            if resolved.is_relative_to(real_root):
                relative = resolved.relative_to(real_root)
                if any(part.startswith(".") for part in relative.parts):
                    return None
                return resolved
        return None

    def download_target(self, output_dir: str | None) -> Path:
        root = self.download_dir
        root.mkdir(parents=True, exist_ok=True)
        directory = root
        if output_dir:
            candidate = Path(output_dir).expanduser()
            directory = candidate if candidate.is_absolute() else root / candidate
        # Check before mkdir so nothing is created outside the root.
        if self._inside(directory, [root]) is None:
            raise ToolError(f"output_dir must be inside {root} (no hidden folders)")
        directory.mkdir(parents=True, exist_ok=True)
        resolved = self._inside(directory, [root])
        if resolved is None:  # a symlink inside the root points elsewhere
            raise ToolError(f"output_dir must be inside {root} (no hidden folders)")
        return resolved

    def upload_source(self, file_path: str) -> Path:
        path = Path(file_path).expanduser()
        roots = [*self.upload_roots, self.download_dir]
        resolved = self._inside(path, roots) if path.exists() else None
        if resolved is None or not resolved.is_file():
            allowed = ", ".join(str(r) for r in roots)
            raise ToolError(
                f"Can only attach existing files (no hidden files or folders) inside: {allowed}. "
                "Start the server with --upload-dir to allow other folders."
            )
        return resolved


def _write_new_file(directory: Path, filename: str, data: bytes) -> Path:
    """Create a new file; never overwrite or follow an existing path or symlink."""
    stem, suffix = Path(filename).stem, Path(filename).suffix
    for counter in range(1000):
        name = filename if counter == 0 else f"{stem} ({counter}){suffix}"
        path = directory / name
        try:
            with path.open("xb") as handle:
                handle.write(data)
        except FileExistsError:
            continue
        return path
    raise ToolError(f"Too many files named {filename} in {directory}")


def _clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)


def _looks_like_html(value: str) -> bool:
    return bool(_HTML_TAG.search(value))


def _readable(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert HTML text fields (body, description, ...) to Markdown."""
    for record in records:
        for key in _HTML_KEYS & record.keys():
            value = record[key]
            if isinstance(value, str) and _looks_like_html(value):
                record[key] = _html_to_markdown(value)
    return records


def _safe_filename(name: str | None, fallback: str) -> str:
    candidate = Path(name or "").name.strip()
    if candidate in {"", ".", ".."}:
        return fallback
    return candidate


def _timesheet_dict(ts: Timesheet) -> dict[str, Any]:
    return {
        "id": ts.id,
        "name": ts.name,
        "project": ts.project_name,
        "source": {"kind": ts.source.kind, "id": ts.source.id, "name": ts.source.name},
        "date": ts.date,
        "hours": round(ts.unit_amount, 4),
        "running": ts.timer_start is not None,
        "elapsed": ts.elapsed_formatted,
    }


class _ClientHolder:
    """Lazily creates one shared AsyncOdooClient for the server's lifetime."""

    def __init__(
        self,
        *,
        config: OdooConfig | None,
        instance: str | None,
        client: AsyncOdooClient | None,
    ) -> None:
        self._config = config
        self._instance = instance
        self._client = client
        self._owns_client = client is None
        self._lock = asyncio.Lock()

    def secrets(self) -> list[str]:
        """Credential values to redact from error messages."""
        config = self._client.config if self._client is not None else self._config
        if config is None:
            return []
        values = [getattr(config, "password", None)]
        values += list((getattr(config, "http_headers", None) or {}).values())
        return _secret_variants([v for v in values if isinstance(v, str) and v])

    async def get(self) -> AsyncOdooClient:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is None:
                config = self._config or get_config(instance=self._instance)
                self._client = AsyncOdooClient(config)
            return self._client

    async def close(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.close()


async def _hide_unavailable_tools(
    server: MCPServer[Any], holder: _ClientHolder, tool_models: dict[str, str]
) -> list[str]:
    """Remove tools whose Odoo model does not exist; return their names.

    Any failure (no connection yet, no access to ``ir.model``) keeps every tool.
    """
    models = sorted({*tool_models.values(), "res.partner"})
    try:
        odoo = await holder.get()
        rows = await odoo.search_read(
            "ir.model", domain=[("model", "in", models)], fields=["model"]
        )
    except Exception as exc:
        logger.warning(
            "Could not check installed Odoo apps (%s); showing all tools", type(exc).__name__
        )
        return []
    found = {row.get("model") for row in rows}
    if "res.partner" not in found:  # an unusable answer: keep everything
        return []
    hidden = sorted(name for name, model in tool_models.items() if model not in found)
    for name in hidden:
        server.remove_tool(name)
    return hidden


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_server(  # noqa: PLR0915
    *,
    config: OdooConfig | None = None,
    instance: str | None = None,
    allow_write: bool = False,
    allow_delete: bool = False,
    client: AsyncOdooClient | None = None,
    download_dir: Path | None = None,
    upload_dirs: list[Path] | None = None,
    hide_unavailable: bool = True,
) -> MCPServer[Any]:
    """Build the Vodoo MCP server.

    Args:
        config: Explicit configuration. Defaults to Vodoo's normal config lookup.
        instance: Instance/profile name used when *config* is not given.
        allow_write: Register tools that create or change data in Odoo.
        allow_delete: Register the record deletion tool.
        client: Pre-built client (mainly for tests); overrides *config*.
        download_dir: The only folder (with subfolders) that downloads may go to.
        upload_dirs: Folders whose files may be attached (default: Downloads,
            Desktop, Documents). The download folder is always allowed.
        hide_unavailable: At startup, hide tools for Odoo apps that are not installed
            (for example Helpdesk or Knowledge on Community).
    """
    holder = _ClientHolder(config=config, instance=instance, client=client)
    files = _FilePolicy(
        download_dir or DEFAULT_DOWNLOAD_DIR,
        list(upload_dirs) if upload_dirs is not None else list(DEFAULT_UPLOAD_DIRS),
    )

    tool_models: dict[str, str] = {}  # tool name -> Odoo model it needs
    hidden: list[str] = []

    @asynccontextmanager
    async def lifespan(app: MCPServer[Any]) -> AsyncIterator[None]:
        if hide_unavailable:
            hidden.extend(await _hide_unavailable_tools(app, holder, tool_models))
        try:
            yield None
        finally:
            await holder.close()

    mode = "read/write" if allow_write else "read-only"
    if allow_delete:
        mode += " + delete"
    server: MCPServer[Any] = MCPServer(
        name=SERVER_NAME,
        title="Odoo (Vodoo)",
        instructions=f"{INSTRUCTIONS}\nServer mode: {mode}.",
        website_url="https://github.com/julian-r/vodoo",
        lifespan=lifespan,
    )

    def register(
        fn: Callable[..., Awaitable[Any]],
        *,
        title: str,
        read_only: bool,
        destructive: bool = False,
        idempotent: bool = False,
        requires: str | None = None,
    ) -> None:
        if requires is not None:
            tool_models[fn.__name__] = requires
        annotations = ToolAnnotations(
            title=title,
            read_only_hint=read_only,
            destructive_hint=None if read_only else destructive,
            idempotent_hint=None if read_only else idempotent,
            open_world_hint=True,
        )
        server.add_tool(
            _as_tool(fn, holder.secrets),
            name=fn.__name__,
            title=title,
            description=inspect.getdoc(fn),
            annotations=annotations,
            structured_output=False,
        )

    async def record_url(odoo: AsyncOdooClient, model: str, record_id: int) -> str:
        await odoo.get_uid()  # ensures the transport (and thus is_json2) is known
        return build_record_url(
            odoo.config.url, model, record_id, "json2" if odoo.is_json2 else "jsonrpc"
        )

    async def readable_fields(odoo: AsyncOdooClient, model: str) -> list[str]:
        """All fields except binary blobs (which can be megabytes of base64)."""
        definitions = await odoo.fields_get(model, attributes=["type"])
        return [name for name, spec in definitions.items() if spec.get("type") != "binary"]

    # -- Read tools ----------------------------------------------------------

    async def odoo_info() -> dict[str, Any]:
        """Show which Odoo instance and user this server uses, and whether writes are enabled."""
        odoo = await holder.get()
        uid = await odoo.get_uid()
        users = await odoo.read("res.users", [uid], ["name", "login", "company_id"])
        user = users[0] if users else {}
        return {
            "url": odoo.config.url,
            "database": odoo.config.database,
            "user": {
                "id": uid,
                "name": user.get("name"),
                "login": user.get("login"),
                "company": user.get("company_id"),
            },
            "api": "json2 (Odoo 19+)" if odoo.is_json2 else "jsonrpc (Odoo 17/18)",
            "write_enabled": allow_write,
            "delete_enabled": allow_delete,
            "hidden_tools": sorted(hidden),
        }

    async def search_records(
        model: Annotated[str, Field(description="Odoo model, e.g. 'res.partner'.")],
        domain: Annotated[
            list[Any] | None, Field(description="Odoo domain; omit for all records.")
        ] = None,
        fields: Annotated[
            list[str] | None,
            Field(description="Fields to return. Omit for a curated default set."),
        ] = None,
        limit: Annotated[int, Field(description=f"Max records (1-{MAX_LIMIT}).")] = 50,
        offset: Annotated[int, Field(ge=0)] = 0,
        order: Annotated[str | None, Field(description="e.g. 'date desc, id desc'.")] = None,
    ) -> dict[str, Any]:
        """Search any Odoo model and return matching records.

        Without `fields`, well-known models (tasks, tickets, invoices, leads, ...)
        return a curated field set and other models return only id and display_name.
        The result includes `total` (all matches) so you can page with `offset`.
        """
        odoo = await holder.get()
        if fields is None:
            known = _KNOWN_MODELS.get(model)
            fields = list(known[0]) if known else ["id", "display_name"]
        limit = _clamp_limit(limit)
        records = await odoo.search_read(
            model, domain=domain or [], fields=fields, limit=limit, offset=offset, order=order
        )
        # A partial page proves the total; a full or empty page (past the end) does not.
        if 0 < len(records) < limit or (not records and offset == 0):
            total = len(records) + offset
        else:
            total = await odoo.execute(model, "search_count", domain=domain or [])
        return {
            "model": model,
            "total": total,
            "count": len(records),
            "records": _readable(records),
        }

    async def count_records(
        model: str,
        domain: list[Any] | None = None,
    ) -> dict[str, Any]:
        """Count records of an Odoo model matching a domain."""
        odoo = await holder.get()
        count = await odoo.execute(model, "search_count", domain=domain or [])
        return {"model": model, "count": count}

    async def read_records(
        model: str,
        ids: Annotated[list[int], Field(description="Record ids.", min_length=1)],
        fields: Annotated[
            list[str] | None,
            Field(description="Fields to read. Omit for detail fields (or all non-binary)."),
        ] = None,
    ) -> list[dict[str, Any]]:
        """Read full records by id from any Odoo model."""
        odoo = await holder.get()
        if fields is None:
            known = _KNOWN_MODELS.get(model)
            detail = known[1] if known else None
            fields = list(detail) if detail else await readable_fields(odoo, model)
        return _readable(await odoo.read(model, ids, fields))

    async def get_fields(
        model: str,
        field_names: Annotated[
            list[str] | None, Field(description="Limit to these fields; omit for all.")
        ] = None,
        attributes: Annotated[
            list[str] | None,
            Field(description=f"Field attributes to return (default {_FIELD_ATTRIBUTES})."),
        ] = None,
    ) -> dict[str, Any]:
        """List the fields of an Odoo model with type, label, relation, and selection values."""
        odoo = await holder.get()
        return await odoo.fields_get(
            model, fields=field_names, attributes=attributes or _FIELD_ATTRIBUTES
        )

    async def name_search(
        model: str,
        name: Annotated[str, Field(description="Text to match against the display name.")],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find record ids by name (e.g. a partner, product, account, journal, or tax)."""
        odoo = await holder.get()
        matches = await odoo.name_search(model, name, limit=_clamp_limit(limit))
        return [{"id": record_id, "name": label} for record_id, label in matches]

    async def get_record_url(model: str, record_id: int) -> dict[str, str]:
        """Get the Odoo web URL of a record (to show or link for the user)."""
        odoo = await holder.get()
        return {"url": await record_url(odoo, model, record_id)}

    async def list_messages(
        model: str,
        record_id: int,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """List chatter messages and notes of a record, newest first (bodies as Markdown)."""
        odoo = await holder.get()
        messages = await odoo.search_read(
            "mail.message",
            domain=[("model", "=", model), ("res_id", "=", record_id)],
            fields=["id", "date", "author_id", "message_type", "subtype_id", "subject", "body"],
            order="date desc",
            limit=_clamp_limit(limit),
        )
        return _readable(messages)

    async def list_attachments(model: str, record_id: int) -> list[dict[str, Any]]:
        """List files attached to a record (e.g. invoice PDFs)."""
        odoo = await holder.get()
        return await odoo.search_read(
            "ir.attachment",
            domain=[("res_model", "=", model), ("res_id", "=", record_id)],
            fields=["id", "name", "mimetype", "file_size", "create_date"],
            order="id desc",
        )

    async def download_attachment(
        attachment_id: int,
        output_dir: Annotated[
            str | None,
            Field(
                description="Subfolder of the download folder (or an absolute path "
                "inside it). Default: the download folder itself."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Download an attachment to the local download folder and return its path.

        The download folder is set by the server (default ~/Downloads/vodoo). Never
        overwrites: an existing file gets a numbered name instead.
        """
        import base64

        odoo = await holder.get()
        rows = await odoo.read("ir.attachment", [attachment_id], ["name", "mimetype", "datas"])
        if not rows or not rows[0].get("datas"):
            raise ToolError(f"Attachment {attachment_id} not found or empty")
        directory = files.download_target(output_dir)
        filename = _safe_filename(rows[0].get("name"), f"attachment_{attachment_id}")
        if filename.startswith("."):
            filename = f"attachment_{attachment_id}{filename}"
        data = base64.b64decode(rows[0]["datas"])
        path = _write_new_file(directory, filename, data)
        return {"path": str(path), "bytes": len(data), "mimetype": rows[0].get("mimetype")}

    # -- Accounting (read) ---------------------------------------------------

    async def list_account_moves(
        move_type: Annotated[
            MoveType | None,
            Field(
                description="out_invoice=customer invoice, out_refund=credit note, "
                "in_invoice=vendor bill, in_refund=vendor refund, entry=journal entry."
            ),
        ] = None,
        state: Literal["draft", "posted", "cancel"] | None = None,
        payment_state: Annotated[
            Literal["not_paid", "in_payment", "paid", "partial", "reversed"] | None,
            Field(description="Payment status of invoices/bills."),
        ] = None,
        partner: Annotated[str | None, Field(description="Partner name (substring).")] = None,
        search: Annotated[
            str | None, Field(description="Match number, reference, payment ref, or origin.")
        ] = None,
        date_from: Annotated[
            str | None, Field(description="Accounting date >= YYYY-MM-DD.")
        ] = None,
        date_to: Annotated[str | None, Field(description="Accounting date <= YYYY-MM-DD.")] = None,
        company: Annotated[str | None, Field(description="Company name (substring).")] = None,
        overdue: Annotated[
            bool, Field(description="Only open moves with a due date before today.")
        ] = False,
        limit: int = 50,
        order: str = "date desc, id desc",
    ) -> dict[str, Any]:
        """List invoices, bills, credit notes, and journal entries (account.move)."""
        domain = build_account_move_domain(
            search=search, company=company, partner=partner, move_type=move_type, state=state
        )
        if payment_state:
            domain.append(("payment_state", "=", payment_state))
        if date_from:
            domain.append(("date", ">=", date_from))
        if date_to:
            domain.append(("date", "<=", date_to))
        if overdue:
            from datetime import date as _date

            domain += [
                ("state", "=", "posted"),
                ("payment_state", "in", ["not_paid", "partial"]),
                ("invoice_date_due", "<", _date.today().isoformat()),  # noqa: DTZ011
            ]
        return await search_records(
            "account.move", domain=domain, fields=_MOVE_SUMMARY_FIELDS, limit=limit, order=order
        )

    async def get_account_move(
        move_id: int,
        include_lines: bool = True,
    ) -> dict[str, Any]:
        """Show one invoice/bill/journal entry with totals, status, and its lines."""
        odoo = await holder.get()
        detail = _GeneratedAccountMoveAttrs._default_detail_fields or []
        fields = list(dict.fromkeys([*detail, "amount_residual", "journal_id", "line_ids"]))
        fields.append("invoice_line_ids")
        rows = await odoo.read("account.move", [move_id], fields)
        if not rows:
            raise ToolError(f"account.move {move_id} not found")
        move = _readable(rows)[0]
        invoice_line_ids = move.pop("invoice_line_ids", []) or []
        line_ids = move.pop("line_ids", []) or []
        if include_lines:
            is_entry = move.get("move_type") == "entry"
            ids = line_ids if is_entry else invoice_line_ids
            move["lines"] = (
                await odoo.read("account.move.line", ids, _MOVE_LINE_FIELDS) if ids else []
            )
        move["url"] = await record_url(odoo, "account.move", move_id)
        return move

    # -- Timesheets (read) ---------------------------------------------------

    async def list_timesheets(
        days: Annotated[int, Field(description="0=today, 7=past week, -1=all time.")] = 0,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List the current user's timesheet entries, including running timers."""
        odoo = await holder.get()
        timesheets = await odoo.timer.list(days=days, limit=_clamp_limit(limit))
        return [_timesheet_dict(ts) for ts in timesheets]

    async def timer_status() -> list[dict[str, Any]]:
        """Show the current user's running timers."""
        odoo = await holder.get()
        return [_timesheet_dict(ts) for ts in await odoo.timer.active()]

    for read_tool, title, *needs in (
        (odoo_info, "Odoo connection info"),
        (search_records, "Search records"),
        (count_records, "Count records"),
        (read_records, "Read records"),
        (get_fields, "List model fields"),
        (name_search, "Find records by name"),
        (get_record_url, "Record URL"),
        (list_messages, "List chatter messages"),
        (list_attachments, "List attachments"),
        (download_attachment, "Download attachment"),
        (list_account_moves, "List invoices / bills / entries", "account.move"),
        (get_account_move, "Show invoice / bill / entry", "account.move"),
        (list_timesheets, "List timesheets", "account.analytic.line"),
        (timer_status, "Running timers", "account.analytic.line"),
    ):
        register(read_tool, title=title, read_only=True, requires=needs[0] if needs else None)

    from vodoo.mcp_server.domains import register_domain_tools

    register_domain_tools(
        register,
        holder,
        files,
        allow_write=allow_write,
        allow_delete=allow_delete,
        record_url=record_url,
    )

    if allow_write:
        _register_write_tools(
            register, holder, record_url, get_account_move, files, allow_delete=allow_delete
        )
    if allow_delete:
        _register_delete_tools(register, holder)

    return server


def _register_write_tools(  # noqa: PLR0915
    register: Callable[..., None],
    holder: _ClientHolder,
    record_url: Callable[[AsyncOdooClient, str, int], Awaitable[str]],
    get_account_move: Callable[..., Awaitable[dict[str, Any]]],
    files: _FilePolicy,
    *,
    allow_delete: bool,
) -> None:
    """Register tools that create or modify Odoo data."""

    def guard_delete(*payloads: Any) -> None:
        _guard_delete(allow_delete, *payloads)

    async def create_record(
        model: str,
        values: Annotated[dict[str, Any], Field(description="Field values for the new record.")],
        context: Annotated[
            dict[str, Any] | None, Field(description="Optional Odoo context.")
        ] = None,
    ) -> dict[str, Any]:
        """Create a record in any Odoo model and return its id and URL."""
        guard_delete(values)
        odoo = await holder.get()
        record_id = await odoo.create(model, values, context=context)
        return {"id": record_id, "url": await record_url(odoo, model, record_id)}

    async def update_records(
        model: str,
        ids: Annotated[list[int], Field(min_length=1)],
        values: Annotated[dict[str, Any], Field(description="Field values to write.")],
        check_write_date: Annotated[
            str | None,
            Field(
                description="Optional UTC 'YYYY-MM-DD HH:MM:SS' write_date you read; the "
                "update is refused if a record changed since (best-effort)."
            ),
        ] = None,
    ) -> dict[str, Any]:
        """Update field values on one or more records of any Odoo model."""
        guard_delete(values)
        odoo = await holder.get()
        ok = await odoo.write(model, ids, values, check_write_date=check_write_date)
        return {"updated": ids if ok else [], "ok": bool(ok)}

    async def call_method(
        model: str,
        method: Annotated[
            str, Field(description="Public model method, e.g. 'action_post' or 'action_confirm'.")
        ],
        ids: Annotated[
            list[int] | None, Field(description="Records to call the method on.")
        ] = None,
        kwargs: Annotated[
            dict[str, Any] | None,
            Field(description="Named arguments (including optional 'context')."),
        ] = None,
    ) -> dict[str, Any]:
        """Call a public method on an Odoo model or records (buttons, actions, helpers).

        Only named arguments are supported (works on Odoo 17-19). Wizards often return an
        action dict describing the next step.
        """
        if method.startswith("_"):
            raise ToolError("Private methods (starting with '_') cannot be called")
        if not allow_delete and "unlink" in method.lower():
            raise ToolError(f"'{method}' deletes records and needs --allow-delete")
        guard_delete(kwargs)
        odoo = await holder.get()
        args: list[Any] = [ids] if ids is not None else []
        result = await odoo.execute(model, method, *args, **(kwargs or {}))
        return {"result": result}

    async def post_message(
        model: str,
        record_id: int,
        message: Annotated[str, Field(description="Message text (Markdown by default).")],
        internal: Annotated[
            bool,
            Field(
                description="True = internal note (default). False = public comment that "
                "followers/customers can see."
            ),
        ] = True,
        markdown: bool = True,
    ) -> dict[str, Any]:
        """Post an internal note (default) or a public comment on a record's chatter."""
        from vodoo._domain import _convert_to_html

        odoo = await holder.get()
        user_id = odoo.config.default_user_id or await odoo.get_uid()
        message_id = await message_post_sudo_with_id(
            odoo,
            model,
            record_id,
            _convert_to_html(message, markdown),
            user_id=user_id,
            is_note=internal,
        )
        return {"message_id": message_id, "internal": internal}

    async def attach_file(
        model: str,
        record_id: int,
        file_path: Annotated[str, Field(description="Path of a local file to upload.")],
        name: Annotated[str | None, Field(description="Attachment name override.")] = None,
    ) -> dict[str, Any]:
        """Upload a local file as an attachment to a record.

        Only files inside the server's allowed folders can be attached (default:
        ~/Downloads, ~/Desktop, ~/Documents; hidden files and folders are refused).
        """
        from vodoo.base import _prepare_attachment_upload

        path = files.upload_source(file_path)
        odoo = await holder.get()
        values = _prepare_attachment_upload(path, None, name, model, record_id)
        attachment_id = await odoo.create("ir.attachment", values)
        return {"attachment_id": attachment_id, "name": values.get("name")}

    # -- Accounting (write) --------------------------------------------------

    async def create_account_move(
        move_type: Annotated[
            MoveType,
            Field(
                description="out_invoice=customer invoice, out_refund=credit note, "
                "in_invoice=vendor bill, in_refund=vendor refund, entry=journal entry."
            ),
        ],
        lines: Annotated[
            list[MoveLine],
            Field(
                description="Invoice lines (name, product_id, quantity, price_unit, tax_ids) "
                "or, for move_type 'entry', balanced journal items (account_id, debit, credit).",
                min_length=1,
            ),
        ],
        partner_id: Annotated[
            int | None, Field(description="Customer/vendor (required except for entries).")
        ] = None,
        invoice_date: Annotated[str | None, Field(description="YYYY-MM-DD.")] = None,
        date: Annotated[
            str | None, Field(description="Accounting date YYYY-MM-DD (entries).")
        ] = None,
        ref: Annotated[str | None, Field(description="Reference / vendor bill number.")] = None,
        journal_id: int | None = None,
        currency_id: int | None = None,
        invoice_date_due: Annotated[str | None, Field(description="Due date YYYY-MM-DD.")] = None,
        payment_reference: str | None = None,
        narration: Annotated[str | None, Field(description="Terms / internal notes.")] = None,
        extra_values: Annotated[
            dict[str, Any] | None, Field(description="Any other account.move field values.")
        ] = None,
        post: Annotated[
            bool, Field(description="Post (validate) right away. Default: keep as draft.")
        ] = False,
    ) -> dict[str, Any]:
        """Create a draft invoice, bill, credit note, or journal entry (optionally post it)."""
        if move_type != "entry" and partner_id is None:
            raise ToolError("partner_id is required for invoices, bills, and refunds")
        odoo = await holder.get()
        line_field = "line_ids" if move_type == "entry" else "invoice_line_ids"
        values: dict[str, Any] = {
            "move_type": move_type,
            line_field: [(0, 0, line.to_values()) for line in lines],
        }
        optional = {
            "partner_id": partner_id,
            "invoice_date": invoice_date,
            "date": date,
            "ref": ref,
            "journal_id": journal_id,
            "currency_id": currency_id,
            "invoice_date_due": invoice_date_due,
            "payment_reference": payment_reference,
            "narration": Markdown(narration) if narration else None,
        }
        values.update({key: value for key, value in optional.items() if value is not None})
        if extra_values:
            values.update(extra_values)
        guard_delete(values)
        move_id = await odoo.create(
            "account.move", values, context={"default_move_type": move_type}
        )
        if post:
            await odoo.execute("account.move", "action_post", [move_id])
        return await get_account_move(move_id)

    async def post_account_moves(
        move_ids: Annotated[list[int], Field(min_length=1)],
    ) -> list[dict[str, Any]]:
        """Post (validate) draft invoices/bills/entries. Assigns their final number."""
        odoo = await holder.get()
        await odoo.execute("account.move", "action_post", move_ids)
        return await odoo.read("account.move", move_ids, _MOVE_SUMMARY_FIELDS)

    async def reset_account_moves_to_draft(
        move_ids: Annotated[list[int], Field(min_length=1)],
    ) -> list[dict[str, Any]]:
        """Reset posted or cancelled moves back to draft so they can be edited."""
        odoo = await holder.get()
        await odoo.execute("account.move", "button_draft", move_ids)
        return await odoo.read("account.move", move_ids, _MOVE_SUMMARY_FIELDS)

    async def cancel_account_moves(
        move_ids: Annotated[list[int], Field(min_length=1)],
    ) -> list[dict[str, Any]]:
        """Cancel draft moves (reset posted moves to draft first)."""
        odoo = await holder.get()
        await odoo.execute("account.move", "button_cancel", move_ids)
        return await odoo.read("account.move", move_ids, _MOVE_SUMMARY_FIELDS)

    async def register_payment(
        move_ids: Annotated[
            list[int], Field(description="Posted invoices/bills to pay.", min_length=1)
        ],
        amount: Annotated[
            float | None, Field(description="Amount; omit to pay the full open amount.")
        ] = None,
        payment_date: Annotated[str | None, Field(description="YYYY-MM-DD; default today.")] = None,
        journal_id: Annotated[
            int | None, Field(description="Bank/cash journal; default from Odoo.")
        ] = None,
        payment_method_line_id: int | None = None,
        memo: Annotated[str | None, Field(description="Payment memo / communication.")] = None,
        group_payments: Annotated[
            bool, Field(description="One payment per partner when paying several moves.")
        ] = True,
    ) -> dict[str, Any]:
        """Register a payment for posted invoices or bills (Odoo's 'Register Payment')."""
        odoo = await holder.get()
        # The wizard itself does not reject cancelled/draft moves on every version
        # (Odoo 18 creates an orphan payment), so check like the UI button does.
        current = await odoo.read(
            "account.move", move_ids, ["name", "state", "payment_state", "amount_residual"]
        )
        found = {row["id"] for row in current}
        problems = [f"{mid}: not found" for mid in move_ids if mid not in found]
        for row in current:
            label = f"{row['id']} ({row.get('name')})"
            if row.get("state") != "posted":
                problems.append(f"{label}: state is {row.get('state')}, must be posted")
            elif row.get("payment_state") in ("paid", "reversed") or not row.get("amount_residual"):
                problems.append(f"{label}: nothing left to pay")
        if problems:
            raise ToolError("Cannot register payment: " + "; ".join(problems))
        context = {"active_model": "account.move", "active_ids": move_ids}
        values: dict[str, Any] = {}
        optional = {
            "amount": amount,
            "payment_date": payment_date,
            "journal_id": journal_id,
            "payment_method_line_id": payment_method_line_id,
            "communication": memo,
        }
        values.update({key: value for key, value in optional.items() if value is not None})
        if len(move_ids) > 1:
            values["group_payment"] = group_payments
        wizard_id = await odoo.create("account.payment.register", values, context=context)
        action = await odoo.execute(
            "account.payment.register", "action_create_payments", [wizard_id], context=context
        )
        payment_ids: list[int] = []
        if isinstance(action, dict):
            if isinstance(action.get("res_id"), int) and action["res_id"]:
                payment_ids = [action["res_id"]]
            elif action.get("domain"):
                payment_ids = await odoo.search("account.payment", action["domain"])
        payments = (
            await odoo.read(
                "account.payment",
                payment_ids,
                ["id", "name", "state", "amount", "date", "partner_id", "journal_id"],
            )
            if payment_ids
            else []
        )
        moves = await odoo.read("account.move", move_ids, _MOVE_SUMMARY_FIELDS)
        return {"payments": payments, "moves": moves}

    # -- Activities & timers -------------------------------------------------

    async def mark_activity_done(activity_id: int) -> dict[str, Any]:
        """Mark a scheduled activity (mail.activity) as done."""
        odoo = await holder.get()
        await odoo.activities.done(activity_id)
        return {"done": activity_id}

    async def timer_start(
        task_id: Annotated[int | None, Field(description="project.task id.")] = None,
        ticket_id: Annotated[int | None, Field(description="helpdesk.ticket id.")] = None,
        timesheet_id: Annotated[
            int | None, Field(description="Existing timesheet line to resume.")
        ] = None,
    ) -> list[dict[str, Any]]:
        """Start a timer on a task, helpdesk ticket, or existing timesheet (give exactly one)."""
        given = [v for v in (task_id, ticket_id, timesheet_id) if v is not None]
        if len(given) != 1:
            raise ToolError("Give exactly one of task_id, ticket_id, or timesheet_id")
        odoo = await holder.get()
        if task_id is not None:
            await odoo.timer.start_task(task_id)
        elif ticket_id is not None:
            await odoo.timer.start_ticket(ticket_id)
        elif timesheet_id is not None:
            await odoo.timer.start_timesheet(timesheet_id)
        return [_timesheet_dict(ts) for ts in await odoo.timer.active()]

    async def timer_stop(
        timesheet_id: Annotated[
            int | None, Field(description="Stop only this timesheet; omit to stop all.")
        ] = None,
    ) -> dict[str, Any]:
        """Stop running timers (all, or one timesheet) and log the time."""
        odoo = await holder.get()
        if timesheet_id is not None:
            await odoo.timer.stop_timesheet(timesheet_id)
            return {"stopped": [timesheet_id]}
        stopped = await odoo.timer.stop()
        return {"stopped": [_timesheet_dict(ts) for ts in stopped]}

    accounting = {
        "create_account_move",
        "post_account_moves",
        "reset_account_moves_to_draft",
        "cancel_account_moves",
        "register_payment",
    }
    tools: list[tuple[Callable[..., Awaitable[Any]], str, bool, bool]] = [
        # (tool, title, destructive, idempotent)
        (create_record, "Create record", False, False),
        (update_records, "Update records", True, True),
        (call_method, "Call model method", True, False),
        (post_message, "Post chatter message", False, False),
        (attach_file, "Attach file", False, False),
        # Destructive: with post=True it assigns a final sequence number.
        (create_account_move, "Create invoice / bill / entry", True, False),
        (post_account_moves, "Post invoices / bills / entries", True, True),
        (reset_account_moves_to_draft, "Reset to draft", True, True),
        (cancel_account_moves, "Cancel invoices / bills / entries", True, True),
        (register_payment, "Register payment", True, False),
        (mark_activity_done, "Mark activity done", True, True),
        (timer_start, "Start timer", False, False),
        (timer_stop, "Stop timer", False, False),
    ]
    for tool, title, destructive, idempotent in tools:
        name = tool.__name__
        requires = None
        if name in accounting:
            requires = "account.move"
        elif name.startswith("timer_"):
            requires = "account.analytic.line"
        register(
            tool,
            title=title,
            read_only=False,
            destructive=destructive,
            idempotent=idempotent,
            requires=requires,
        )


def _register_delete_tools(register: Callable[..., None], holder: _ClientHolder) -> None:
    """Register tools that permanently delete Odoo data."""

    async def delete_records(
        model: str,
        ids: Annotated[list[int], Field(min_length=1)],
    ) -> dict[str, Any]:
        """Permanently delete records. Prefer archiving (active=False) where possible."""
        odoo = await holder.get()
        ok = await odoo.unlink(model, ids)
        return {"deleted": ids if ok else [], "ok": bool(ok)}

    register(delete_records, title="Delete records", read_only=False, destructive=True)


def _quiet_http_logs() -> None:
    """Silence HTTP client logs: one line per request floods the client's server log,
    and their DEBUG lines can contain request headers (credentials)."""
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def run(
    *,
    instance: str | None = None,
    allow_write: bool = False,
    allow_delete: bool = False,
    config: OdooConfig | None = None,
    download_dir: Path | None = None,
    upload_dirs: list[Path] | None = None,
) -> None:
    """Run the Vodoo MCP server over stdio (blocking)."""
    _quiet_http_logs()
    if config is None:
        # Validate configuration up front so a broken setup fails fast with a clear
        # message on stderr instead of on the first tool call.
        config = get_config(instance=instance)
    server = create_server(
        config=config,
        instance=instance,
        allow_write=allow_write,
        allow_delete=allow_delete,
        download_dir=download_dir,
        upload_dirs=upload_dirs,
    )
    server.run("stdio")
