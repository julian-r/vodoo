"""Odoo Documents operations for Vodoo."""

from __future__ import annotations

import base64
import mimetypes
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.cmd import Cmd
from vodoo.exceptions import RecordNotFoundError, VodooError

_LEGACY_FOLDER_FIELDS = ["id", "name", "parent_folder_id"]
_MODERN_FOLDER_FIELDS = ["id", "name", "folder_id"]


@dataclass(frozen=True)
class DocumentUploadResult:
    """The record created by a Documents upload."""

    document_id: int
    url: str


class _DocumentAttrs:
    _model = "documents.document"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "folder_id",
        "mimetype",
        "file_size",
        "create_date",
    ]
    _default_detail_fields: ClassVar[list[str] | None] = _default_fields
    _record_type = "Document"


def _uses_document_folder_records(fields: dict[str, Any]) -> bool:
    """Return whether ``documents.document`` includes folders in its type selection."""
    selection = fields.get("type", {}).get("selection") or []
    if isinstance(selection, dict):
        return "folder" in selection
    return any(
        isinstance(option, (list, tuple)) and option and option[0] == "folder"
        for option in selection
    )


def _normalize_modern_folders(folders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose modern document folders using the legacy public parent field name."""
    return [
        {
            "id": folder["id"],
            "name": folder["name"],
            "parent_folder_id": folder.get("folder_id"),
        }
        for folder in folders
    ]


def _relation_id(value: Any) -> int | None:
    """Extract an ID from an Odoo Many2one value."""
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)) and value and isinstance(value[0], int):
        return value[0]
    return None


def _order_folder_tree(folders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return folders in hierarchy order with depth and full path metadata."""
    by_id = {folder["id"]: folder for folder in folders}
    children: dict[int | None, list[dict[str, Any]]] = {}
    for folder in folders:
        parent_id = _relation_id(folder.get("parent_folder_id"))
        if parent_id not in by_id:
            parent_id = None
        children.setdefault(parent_id, []).append(folder)

    for siblings in children.values():
        siblings.sort(key=lambda folder: (str(folder.get("name", "")).casefold(), folder["id"]))

    result: list[dict[str, Any]] = []
    visited: set[int] = set()

    def visit(folder: dict[str, Any], depth: int, parents: tuple[str, ...]) -> None:
        folder_id = folder["id"]
        if folder_id in visited:
            return
        visited.add(folder_id)
        name = str(folder.get("name", ""))
        result.append({**folder, "depth": depth, "path": " / ".join((*parents, name))})
        for child in children.get(folder_id, []):
            visit(child, depth + 1, (*parents, name))

    for root in children.get(None, []):
        visit(root, 0, ())

    # Cyclic or malformed hierarchies remain discoverable.
    for folder in sorted(
        folders, key=lambda item: (str(item.get("name", "")).casefold(), item["id"])
    ):
        visit(folder, 0, ())
    return result


def _folder_domain(modern: bool, name: str | None = None) -> list[Any]:
    """Build a folder search domain for legacy and modern Documents schemas."""
    domain: list[Any] = [("type", "=", "folder")] if modern else []
    if name is not None:
        domain.append(("name", "=", name))
    return domain


def _prepare_document_values(
    file_path: Path | str,
    *,
    folder_id: int,
    name: str | None = None,
    tag_ids: list[int] | None = None,
    owner_id: int | None = None,
) -> dict[str, Any]:
    """Validate and encode a local file for ``documents.document.create``."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {path}")

    values: dict[str, Any] = {
        "name": name or path.name,
        "datas": base64.b64encode(path.read_bytes()).decode("ascii"),
        "mimetype": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
        "folder_id": folder_id,
    }
    if tag_ids:
        values["tag_ids"] = [Cmd.set(tag_ids)]
    if owner_id is not None:
        values["owner_id"] = owner_id
    return values


def _numeric_id(value: str | int) -> int | None:
    if isinstance(value, int):
        parsed = value
    else:
        try:
            parsed = int(value)
        except ValueError:
            return None
    if parsed <= 0:
        raise VodooError("Record IDs must be positive integers")
    return parsed


def _require_unique_id(records: list[dict[str, Any]], model: str, value: str) -> int:
    if not records:
        raise VodooError(f"No {model} record found matching '{value}'")
    if len(records) > 1:
        raise VodooError(f"Multiple {model} records match '{value}'; use a numeric ID")
    return int(records[0]["id"])


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def _safe_document_filename(name: Any, document_id: int) -> str:
    """Return a cross-platform basename safe for a local output directory."""
    filename = str(name or "").replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename).rstrip(". ")
    stem = filename.split(".", maxsplit=1)[0].upper()
    if stem in _WINDOWS_RESERVED_NAMES:
        filename = f"_{filename}"
    if filename in {"", ".", ".."}:
        return f"document_{document_id}"
    return filename


def _decode_document_data(document: dict[str, Any], document_id: int) -> bytes:
    """Decode document data, preserving normalized zero-byte binary files."""
    data = document.get("datas")
    if data is not None and data is not False:
        return base64.b64decode(data)
    if document.get("type") == "binary" and document.get("file_size") == 0:
        return b""
    raise RecordNotFoundError("documents.document", document_id)


class DocumentNamespace(_DocumentAttrs, DomainNamespace):
    """Namespace for the ``documents.document`` model."""

    def _uses_document_folder_records(self) -> bool:
        fields = self._client.fields_get(self._model, fields=["type"], attributes=["selection"])
        return _uses_document_folder_records(fields)

    def folders(self, *, tree: bool = False, limit: int | None = 50) -> list[dict[str, Any]]:
        """List accessible folders, normalizing parent relationships across Odoo versions."""
        modern = self._uses_document_folder_records()
        model = self._model if modern else "documents.folder"
        fields = list(_MODERN_FOLDER_FIELDS if modern else _LEGACY_FOLDER_FIELDS)
        records = self._client.search_read(
            model,
            domain=_folder_domain(modern),
            fields=fields,
            limit=limit,
            order="name, id",
        )
        folders = _normalize_modern_folders(records) if modern else records
        return _order_folder_tree(folders) if tree else folders

    def resolve_folder(self, folder: int | str) -> int:
        """Resolve a positive folder ID or exact folder name to its record ID."""
        numeric_id = _numeric_id(folder)
        if numeric_id is not None:
            return numeric_id
        return self._resolve_folder(str(folder), None)

    def _resolve_folder(self, folder: str | None, folder_id: int | None) -> int:
        if (folder is None) == (folder_id is None):
            raise VodooError("Specify exactly one of folder or folder_id")
        if folder_id is not None:
            if folder_id <= 0:
                raise VodooError("folder_id must be a positive integer")
            return folder_id

        assert folder is not None
        modern = self._uses_document_folder_records()
        model = self._model if modern else "documents.folder"
        records = self._client.search_read(
            model,
            domain=_folder_domain(modern, folder),
            fields=["id", "name"],
            limit=2,
        )
        return _require_unique_id(records, model, folder)

    def _resolve_named_record(self, model: str, value: str | int) -> int:
        numeric_id = _numeric_id(value)
        if numeric_id is not None:
            return numeric_id
        text = str(value)
        fields = ["id", "name"]
        if model == "res.users":
            domain: list[Any] = ["|", ("login", "=", text), ("name", "=", text)]
            fields.append("login")
        else:
            domain = [("name", "=", text)]
        records = self._client.search_read(model, domain=domain, fields=fields, limit=2)
        return _require_unique_id(records, model, text)

    def upload(
        self,
        file_path: Path | str,
        *,
        folder: str | None = None,
        folder_id: int | None = None,
        tags: list[str | int] | None = None,
        owner: str | int | None = None,
        name: str | None = None,
    ) -> DocumentUploadResult:
        """Upload a file, specifying exactly one of ``folder`` or ``folder_id``.

        Optional tags and owner may be resolved by positive ID or exact name.
        """
        resolved_folder_id = self._resolve_folder(folder, folder_id)
        tag_ids = [self._resolve_named_record("documents.tag", tag) for tag in tags or []]
        owner_id = self._resolve_named_record("res.users", owner) if owner is not None else None
        values = _prepare_document_values(
            file_path,
            folder_id=resolved_folder_id,
            name=name,
            tag_ids=tag_ids,
            owner_id=owner_id,
        )
        document_id = self._client.create(self._model, values)
        return DocumentUploadResult(document_id=document_id, url=self.url(document_id))

    def download_file(self, document_id: int, output: Path | str | None = None) -> Path:
        """Download a document and return the resolved output path."""
        records = self._client.read(
            self._model,
            [document_id],
            fields=["name", "type", "file_size", "datas"],
        )
        if not records:
            raise RecordNotFoundError(self._model, document_id)

        document = records[0]
        data = _decode_document_data(document, document_id)
        filename = _safe_document_filename(document.get("name"), document_id)
        output_path = Path(output) if output is not None else Path.cwd() / filename
        if output_path.is_dir():
            output_path /= filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(data)
        return output_path.resolve()
