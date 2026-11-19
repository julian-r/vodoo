"""Shared helpers for the Vodoo MCP server modules.

Safety (error redaction, the delete guard, local file confinement), result
serialization, paging, and the lazily created shared client.
"""

import asyncio
import functools
import json
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx2 as httpx
from mcp.server.mcpserver.exceptions import ToolError

from vodoo.aio.client import AsyncOdooClient
from vodoo.base import _html_to_markdown
from vodoo.config import OdooConfig, get_config
from vodoo.exceptions import VodooError

SERVER_NAME = "vodoo"
MAX_LIMIT = 500
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads" / "vodoo"
DEFAULT_UPLOAD_DIRS = (
    Path.home() / "Downloads",
    Path.home() / "Desktop",
    Path.home() / "Documents",
)


logger = logging.getLogger("vodoo.mcp_server")

_HTML_KEYS = {"body", "description", "narration", "note"}
_HTML_TAG = re.compile(r"<[a-zA-Z/][^>]*>")


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


def as_tool[**P](
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


def contains_delete_command(value: Any) -> bool:
    """True if *value* holds an x2many delete command at any depth.

    Odoo compares the command code with ``==``, so ``[2, id]``, ``[2.0, id, 0]`` and
    forms with extra elements all delete. Any list whose first element equals 2 and
    whose second element is a number counts as a delete command.
    """
    if isinstance(value, dict):
        return any(contains_delete_command(v) for v in value.values())
    if isinstance(value, list | tuple):
        for item in value:
            if isinstance(item, list | tuple) and item and _is_number(item[0]):
                # An x2many command. Only its values dicts can nest more commands;
                # the id list of [6, 0, ids] holds plain ids.
                if item[0] == 2 and len(item) >= 2 and _is_number(item[1]):
                    return True
                if any(isinstance(part, dict) and contains_delete_command(part) for part in item):
                    return True
            elif contains_delete_command(item):
                return True
    return False


def guard_delete(allow_delete: bool, *payloads: Any) -> None:
    """Keep deletion behind --allow-delete, also inside x2many commands."""
    if not allow_delete and any(contains_delete_command(p) for p in payloads):
        raise ToolError(
            "The x2many command [2, id, 0] deletes records and needs a server started "
            "with --allow-delete. Use [3, id, 0] to unlink without deleting."
        )


class FilePolicy:
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


def write_new_file(directory: Path, filename: str, data: bytes) -> Path:
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


def clamp_limit(limit: int) -> int:
    if limit < 1:
        return 1
    return min(limit, MAX_LIMIT)


def _looks_like_html(value: str) -> bool:
    return bool(_HTML_TAG.search(value))


def readable(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert HTML text fields (body, description, ...) to Markdown."""
    for record in records:
        for key in _HTML_KEYS & record.keys():
            value = record[key]
            if isinstance(value, str) and _looks_like_html(value):
                record[key] = _html_to_markdown(value)
    return records


def safe_filename(name: str | None, fallback: str) -> str:
    candidate = Path(name or "").name.strip()
    if candidate in {"", ".", ".."}:
        return fallback
    return candidate


class ClientHolder:
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


def check_extra(extra: dict[str, Any] | None, named: dict[str, str]) -> None:
    """Refuse extra values for fields that have their own parameter (field -> parameter)."""
    clashes = sorted(set(extra or {}) & set(named))
    if clashes:
        hint = ", ".join(f"'{field}' -> use '{named[field]}'" for field in clashes)
        raise ToolError(f"Set these with their own parameter, not in extra values: {hint}")


async def search_page(
    odoo: AsyncOdooClient,
    model: str,
    domain: list[Any],
    fields: list[str],
    limit: int,
    offset: int = 0,
    order: str | None = None,
) -> dict[str, Any]:
    """search_read one page plus the total number of matches."""
    limit = clamp_limit(limit)
    records = await odoo.search_read(
        model, domain=domain, fields=fields, limit=limit, offset=offset, order=order
    )
    # A partial page proves the total; a full or empty page (past the end) does not.
    if 0 < len(records) < limit or (not records and offset == 0):
        total = len(records) + offset
    else:
        total = await odoo.execute(model, "search_count", domain=domain)
    return {"model": model, "total": total, "count": len(records), "records": readable(records)}
