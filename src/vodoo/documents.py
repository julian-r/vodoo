"""Odoo Documents operations for Vodoo."""

from __future__ import annotations

import base64
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


class DocumentNamespace(_DocumentAttrs, DomainNamespace):
    """Namespace for the ``documents.document`` model."""

    def resolve_folder(self, folder: int | str) -> int:
        """Resolve a folder ID or exact folder name to its record ID."""
        if isinstance(folder, int) or folder.isdigit():
            return int(folder)

        matches = self._client.search_read(
            self._model,
            domain=[("type", "=", "folder"), ("name", "=", folder)],
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
        return self.list(
            domain=[("type", "=", "folder")],
            fields=["id", "name", "folder_id", "create_date"],
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
        records = self._client.read(self._model, [document_id], fields=["name", "datas"])
        if not records or not records[0].get("datas"):
            raise RecordNotFoundError(self._model, document_id)

        document = records[0]
        filename = str(document.get("name") or f"document_{document_id}")
        output_path = Path(output) if output is not None else Path.cwd() / filename
        if output_path.is_dir():
            output_path /= filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(base64.b64decode(document["datas"]))
        return output_path.resolve()
