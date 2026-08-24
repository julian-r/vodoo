"""Odoo Documents operations for Vodoo."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.exceptions import RecordNotFoundError, VodooError


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


def _folder_domain(folder_model: str, name: str | None = None) -> list[Any]:
    """Build a folder search domain for old and new Documents schemas."""
    domain: list[Any] = []
    if folder_model == "documents.document":
        domain.append(("type", "=", "folder"))
    if name is not None:
        domain.append(("name", "=", name))
    return domain


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

    def _folder_model(self) -> str:
        fields = self._client.fields_get(
            self._model,
            fields=["folder_id"],
            attributes=["relation"],
        )
        relation = fields.get("folder_id", {}).get("relation")
        if not isinstance(relation, str) or not relation:
            raise VodooError("Could not determine the Odoo Documents folder model")
        return relation

    def resolve_folder(self, folder: int | str) -> int:
        """Resolve a folder ID or exact folder name to its record ID."""
        if isinstance(folder, int) or folder.isdigit():
            return int(folder)

        folder_model = self._folder_model()
        matches = self._client.search_read(
            folder_model,
            domain=_folder_domain(folder_model, folder),
            fields=["id", "name"],
            limit=2,
            order="id",
        )
        if not matches:
            raise VodooError(f"Document folder not found: {folder}")
        if len(matches) > 1:
            raise VodooError(f"Multiple document folders named '{folder}' found; use a folder ID")
        return int(matches[0]["id"])

    def folders(self, limit: int | None = 50) -> list[dict[str, Any]]:
        """List available document folders."""
        folder_model = self._folder_model()
        return self._client.search_read(
            folder_model,
            domain=_folder_domain(folder_model),
            fields=["id", "name"],
            limit=limit,
            order="name, id",
        )

    def upload(
        self,
        file_path: Path | str,
        *,
        folder: int | str,
        name: str | None = None,
    ) -> int:
        """Upload a local file to an Odoo Documents folder."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        values = {
            "name": name or path.name,
            "folder_id": self.resolve_folder(folder),
            "datas": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
        return self._client.create(self._model, values)

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
