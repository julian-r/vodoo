"""Async base class for domain-specific namespaces on AsyncOdooClient.

Mirrors :class:`vodoo._domain.DomainNamespace` with ``async`` methods.
"""

from __future__ import annotations

import builtins
from pathlib import Path
from typing import TYPE_CHECKING, Any

from vodoo._domain import _convert_to_html, _NamespaceBase
from vodoo.aio.auth import message_post_sudo
from vodoo.exceptions import RecordNotFoundError

if TYPE_CHECKING:
    from vodoo.aio.client import AsyncOdooClient


class AsyncDomainNamespace(_NamespaceBase):
    """Async domain namespace — common CRUD, messaging, tags, and attachments."""

    def __init__(self, client: AsyncOdooClient) -> None:
        self._client = client

    # -- CRUD ----------------------------------------------------------------

    async def list(
        self,
        domain: builtins.list[Any] | None = None,
        limit: int | None = 50,
        fields: builtins.list[str] | None = None,
        order: str = "create_date desc",
    ) -> builtins.list[dict[str, Any]]:
        """Search and return records."""
        if fields is None:
            fields = list(self._default_fields)
        return await self._client.search_read(
            self._model,
            domain=domain,
            fields=fields,
            limit=limit,
            order=order,
        )

    async def get(
        self,
        record_id: int,
        fields: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        """Read a single record by ID."""
        if fields is None and self._default_detail_fields is not None:
            fields = list(self._default_detail_fields)
        records = await self._client.read(self._model, [record_id], fields=fields)
        if not records:
            raise RecordNotFoundError(self._model, record_id)
        return records[0]

    async def set(
        self,
        record_id: int,
        values: dict[str, Any],
    ) -> bool:
        """Update fields on a record."""
        return await self._client.write(self._model, [record_id], values)

    async def fields(self) -> dict[str, Any]:
        """Return all field definitions for this model."""
        result: dict[str, Any] = await self._client.execute(self._model, "fields_get")
        return result

    # -- Messaging -----------------------------------------------------------

    async def comment(
        self,
        record_id: int,
        message: str,
        user_id: int | None = None,
        markdown: bool = True,
    ) -> bool:
        """Post a customer-visible comment on a record."""
        body = _convert_to_html(message, markdown)
        return await message_post_sudo(
            self._client,
            self._model,
            record_id,
            body,
            user_id=user_id,
            is_note=False,
        )

    async def note(
        self,
        record_id: int,
        message: str,
        user_id: int | None = None,
        markdown: bool = True,
    ) -> bool:
        """Post an internal note (not visible to customers)."""
        body = _convert_to_html(message, markdown)
        return await message_post_sudo(
            self._client,
            self._model,
            record_id,
            body,
            user_id=user_id,
            is_note=True,
        )

    async def messages(
        self,
        record_id: int,
        limit: int | None = None,
    ) -> builtins.list[dict[str, Any]]:
        """List chatter messages for a record."""
        domain: builtins.list[Any] = [
            ("model", "=", self._model),
            ("res_id", "=", record_id),
        ]
        return await self._client.search_read(
            "mail.message",
            domain=domain,
            fields=self._MESSAGE_FIELDS,
            order="date desc",
            limit=limit,
        )

    # -- Tags ----------------------------------------------------------------

    async def tags(self) -> builtins.list[dict[str, Any]]:
        """List available tags for this domain."""
        if self._tag_model is None:
            msg = f"No tag model defined for {self._model}"
            raise ValueError(msg)
        return await self._client.search_read(
            self._tag_model,
            fields=self._TAG_FIELDS,
            order="name",
        )

    async def add_tag(
        self,
        record_id: int,
        tag_id: int,
    ) -> bool:
        """Add a tag to a record (idempotent)."""
        record = await self.get(record_id, fields=["tag_ids"])
        current_tags: builtins.list[int] = record.get("tag_ids", [])
        if tag_id not in current_tags:
            current_tags.append(tag_id)
            return await self._client.write(
                self._model,
                [record_id],
                {"tag_ids": [(6, 0, current_tags)]},
            )
        return True

    # -- Attachments ---------------------------------------------------------

    async def attachments(
        self,
        record_id: int,
    ) -> builtins.list[dict[str, Any]]:
        """List attachments on a record."""
        domain: builtins.list[Any] = [
            ("res_model", "=", self._model),
            ("res_id", "=", record_id),
        ]
        return await self._client.search_read(
            "ir.attachment",
            domain=domain,
            fields=self._ATTACHMENT_LIST_FIELDS,
        )

    async def attach(
        self,
        record_id: int,
        file_path: Path | str | None = None,
        *,
        data: bytes | None = None,
        name: str | None = None,
    ) -> int:
        """Attach a file (from disk or bytes) to a record."""
        from vodoo.base import _prepare_attachment_upload

        values = _prepare_attachment_upload(file_path, data, name, self._model, record_id)
        return await self._client.create("ir.attachment", values)

    async def download(
        self,
        record_id: int,
        output_dir: Path | None = None,
        extension: str | None = None,
    ) -> builtins.list[Path]:
        """Download all attachments for a record to disk."""
        from vodoo.aio.base import download_record_attachments

        return await download_record_attachments(
            self._client,
            self._model,
            record_id,
            output_dir,
            extension=extension,
        )

    async def attachment_data(
        self,
        attachment_id: int,
    ) -> bytes:
        """Read an attachment and return raw binary content."""
        from vodoo.base import _decode_attachment_data

        attachments = await self._client.read(
            "ir.attachment", [attachment_id], self._ATTACHMENT_READ_FIELDS
        )
        if not attachments:
            raise RecordNotFoundError("ir.attachment", attachment_id)
        return _decode_attachment_data(attachments[0], attachment_id)

    async def all_attachment_data(
        self,
        record_id: int,
    ) -> builtins.list[tuple[int, str, bytes]]:
        """Read all attachments for a record, returning in-memory data."""
        from vodoo.base import _decode_attachment_record

        att_list = await self.attachments(record_id)
        result: builtins.list[tuple[int, str, bytes]] = []
        for att_meta in att_list:
            att_id = att_meta["id"]
            try:
                att_data = await self._client.read(
                    "ir.attachment",
                    [att_id],
                    ["id", *self._ATTACHMENT_READ_FIELDS],
                )
                if not att_data:
                    continue
                decoded = _decode_attachment_record(att_data[0], att_id)
                if decoded is not None:
                    result.append(decoded)
            except Exception:
                continue
        return result

    # -- URL -----------------------------------------------------------------

    def url(self, record_id: int) -> str:
        """Return the Odoo web URL for a record."""
        base_url = self._client.config.url.rstrip("/")
        return f"{base_url}/web#id={record_id}&model={self._model}&view_type=form"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
