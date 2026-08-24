"""Async Odoo Documents operations for Vodoo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.documents import (
    _LEGACY_FOLDER_FIELDS,
    _MODERN_FOLDER_FIELDS,
    _decode_document_data,
    _DocumentAttrs,
    _folder_domain,
    _normalize_modern_folders,
    _numeric_id,
    _order_folder_tree,
    _prepare_document_values,
    _require_unique_id,
    _safe_document_filename,
    _uses_document_folder_records,
)
from vodoo.exceptions import RecordNotFoundError, VodooError


class AsyncDocumentNamespace(_DocumentAttrs, AsyncDomainNamespace):
    """Async namespace for the ``documents.document`` model."""

    async def _uses_document_folder_records(self) -> bool:
        fields = await self._client.fields_get(
            self._model, fields=["type"], attributes=["selection"]
        )
        return _uses_document_folder_records(fields)

    async def folders(self, limit: int | None = 50, *, tree: bool = False) -> list[dict[str, Any]]:
        """List accessible folders, normalizing parent relationships across Odoo versions."""
        modern = await self._uses_document_folder_records()
        model = self._model if modern else "documents.folder"
        fields = list(_MODERN_FOLDER_FIELDS if modern else _LEGACY_FOLDER_FIELDS)
        records = await self._client.search_read(
            model,
            domain=_folder_domain(modern),
            fields=fields,
            limit=limit,
            order="name, id",
        )
        folders = _normalize_modern_folders(records) if modern else records
        return _order_folder_tree(folders) if tree else folders

    async def resolve_folder(self, folder: int | str) -> int:
        """Resolve a positive folder ID or exact folder name to its record ID."""
        numeric_id = _numeric_id(folder)
        if numeric_id is not None:
            return numeric_id
        return await self._resolve_folder(str(folder), None)

    async def _resolve_folder(self, folder: int | str | None, folder_id: int | None) -> int:
        if (folder is None) == (folder_id is None):
            raise VodooError("Specify exactly one of folder or folder_id")
        if folder_id is not None:
            if folder_id <= 0:
                raise VodooError("folder_id must be a positive integer")
            return folder_id

        assert folder is not None
        numeric_id = _numeric_id(folder)
        if numeric_id is not None:
            return numeric_id

        folder_name = str(folder)
        modern = await self._uses_document_folder_records()
        model = self._model if modern else "documents.folder"
        records = await self._client.search_read(
            model,
            domain=_folder_domain(modern, folder_name),
            fields=["id", "name"],
            limit=2,
        )
        return _require_unique_id(records, model, folder_name)

    async def _resolve_named_record(self, model: str, value: str | int) -> int:
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
        records = await self._client.search_read(model, domain=domain, fields=fields, limit=2)
        return _require_unique_id(records, model, text)

    async def upload(
        self,
        file_path: Path | str,
        *,
        folder: int | str | None = None,
        folder_id: int | None = None,
        tags: list[str | int] | None = None,
        owner: str | int | None = None,
        name: str | None = None,
    ) -> int:
        """Upload a file, specifying exactly one of ``folder`` or ``folder_id``.

        Optional tags and owner may be resolved by positive ID or exact name.
        """
        resolved_folder_id = await self._resolve_folder(folder, folder_id)
        tag_ids = [await self._resolve_named_record("documents.tag", tag) for tag in tags or []]
        owner_id = (
            await self._resolve_named_record("res.users", owner) if owner is not None else None
        )
        values = _prepare_document_values(
            file_path,
            folder_id=resolved_folder_id,
            name=name,
            tag_ids=tag_ids,
            owner_id=owner_id,
        )
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
