"""Async Odoo Documents operations for Vodoo."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.documents import (
    _decode_document_data,
    _DocumentAttrs,
    _folder_domain,
    _safe_document_filename,
)
from vodoo.exceptions import RecordNotFoundError, VodooError


class AsyncDocumentNamespace(_DocumentAttrs, AsyncDomainNamespace):
    """Async namespace for the ``documents.document`` model."""

    async def _folder_model(self) -> str:
        fields = await self._client.fields_get(
            self._model,
            fields=["folder_id"],
            attributes=["relation"],
        )
        relation = fields.get("folder_id", {}).get("relation")
        if not isinstance(relation, str) or not relation:
            raise VodooError("Could not determine the Odoo Documents folder model")
        return relation

    async def resolve_folder(self, folder: int | str) -> int:
        """Resolve a folder ID or exact folder name to its record ID."""
        if isinstance(folder, int) or folder.isdigit():
            return int(folder)

        folder_model = await self._folder_model()
        matches = await self._client.search_read(
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

    async def folders(self, limit: int | None = 50) -> list[dict[str, Any]]:
        """List available document folders."""
        folder_model = await self._folder_model()
        return await self._client.search_read(
            folder_model,
            domain=_folder_domain(folder_model),
            fields=["id", "name"],
            limit=limit,
            order="name, id",
        )

    async def upload(
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
            "folder_id": await self.resolve_folder(folder),
            "datas": base64.b64encode(path.read_bytes()).decode("ascii"),
        }
        return await self._client.create(self._model, values)

    async def download_file(self, document_id: int, output: Path | str | None = None) -> Path:
        """Download a document and return the resolved output path."""
        records = await self._client.read(
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
