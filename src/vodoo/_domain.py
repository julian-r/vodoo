"""Base class for domain-specific namespaces on OdooClient.

Each Odoo model domain (helpdesk, CRM, project tasks, etc.) is exposed as a
namespace on the client::

    client.helpdesk.list(limit=10)
    client.helpdesk.get(42)
    client.helpdesk.comment(42, "Deployed to staging")

Subclasses set class-level attributes (``_model``, ``_default_fields``, etc.)
and optionally override or add domain-specific methods (e.g. ``create``).
"""

from __future__ import annotations

import base64
import builtins
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from vodoo.auth import message_post_sudo
from vodoo.exceptions import RecordNotFoundError

if TYPE_CHECKING:
    from vodoo.client import OdooClient


class DomainNamespace:
    """Sync domain namespace — common CRUD, messaging, tags, and attachments.

    Subclasses must set at least ``_model`` and ``_default_fields``.
    """

    _model: ClassVar[str]
    _tag_model: ClassVar[str | None] = None
    _default_fields: ClassVar[list[str]]
    _default_detail_fields: ClassVar[list[str] | None] = None
    _record_type: ClassVar[str] = "Record"

    # Shared field lists (match base.py constants)
    _TAG_FIELDS: ClassVar[list[str]] = ["id", "name", "color"]
    _MESSAGE_FIELDS: ClassVar[list[str]] = [
        "id",
        "date",
        "author_id",
        "body",
        "subject",
        "message_type",
        "subtype_id",
        "email_from",
    ]
    _ATTACHMENT_LIST_FIELDS: ClassVar[list[str]] = [
        "id",
        "name",
        "file_size",
        "mimetype",
        "create_date",
    ]
    _ATTACHMENT_READ_FIELDS: ClassVar[list[str]] = ["name", "datas"]

    def __init__(self, client: OdooClient) -> None:
        self._client = client

    # -- CRUD ----------------------------------------------------------------

    def list(
        self,
        domain: builtins.list[Any] | None = None,
        limit: int | None = 50,
        fields: builtins.list[str] | None = None,
        order: str = "create_date desc",
    ) -> builtins.list[dict[str, Any]]:
        """Search and return records.

        Args:
            domain: Odoo domain filter.
            limit: Max records to return.
            fields: Fields to fetch (``None`` → default fields).
            order: Sort order expression.

        Returns:
            List of record dictionaries.
        """
        if fields is None:
            fields = list(self._default_fields)
        return self._client.search_read(
            self._model,
            domain=domain,
            fields=fields,
            limit=limit,
            order=order,
        )

    def get(
        self,
        record_id: int,
        fields: builtins.list[str] | None = None,
    ) -> dict[str, Any]:
        """Read a single record by ID.

        Args:
            record_id: Record ID.
            fields: Fields to read (``None`` → all fields).

        Returns:
            Record dictionary.

        Raises:
            RecordNotFoundError: If no record with that ID exists.
        """
        if fields is None and self._default_detail_fields is not None:
            fields = list(self._default_detail_fields)
        records = self._client.read(self._model, [record_id], fields=fields)
        if not records:
            raise RecordNotFoundError(self._model, record_id)
        return records[0]

    def set(
        self,
        record_id: int,
        values: dict[str, Any],
    ) -> bool:
        """Update fields on a record.

        Args:
            record_id: Record ID.
            values: Field names → new values.

        Returns:
            ``True`` on success.
        """
        return self._client.write(self._model, [record_id], values)

    def fields(self) -> dict[str, Any]:
        """Return all field definitions for this model."""
        result: dict[str, Any] = self._client.execute(self._model, "fields_get")
        return result

    # -- Messaging -----------------------------------------------------------

    def comment(
        self,
        record_id: int,
        message: str,
        user_id: int | None = None,
        markdown: bool = True,
    ) -> bool:
        """Post a customer-visible comment on a record.

        Args:
            record_id: Record ID.
            message: Comment text (plain or markdown).
            user_id: Post as this user (``None`` → configured default).
            markdown: Convert markdown to HTML before posting.

        Returns:
            ``True`` on success.
        """
        body = _convert_to_html(message, markdown)
        return message_post_sudo(
            self._client,
            self._model,
            record_id,
            body,
            user_id=user_id,
            is_note=False,
        )

    def note(
        self,
        record_id: int,
        message: str,
        user_id: int | None = None,
        markdown: bool = True,
    ) -> bool:
        """Post an internal note (not visible to customers).

        Args:
            record_id: Record ID.
            message: Note text (plain or markdown).
            user_id: Post as this user (``None`` → configured default).
            markdown: Convert markdown to HTML before posting.

        Returns:
            ``True`` on success.
        """
        body = _convert_to_html(message, markdown)
        return message_post_sudo(
            self._client,
            self._model,
            record_id,
            body,
            user_id=user_id,
            is_note=True,
        )

    def messages(
        self,
        record_id: int,
        limit: int | None = None,
    ) -> builtins.list[dict[str, Any]]:
        """List chatter messages for a record.

        Args:
            record_id: Record ID.
            limit: Max messages (``None`` → all).

        Returns:
            List of message dictionaries.
        """
        domain: builtins.list[Any] = [
            ("model", "=", self._model),
            ("res_id", "=", record_id),
        ]
        return self._client.search_read(
            "mail.message",
            domain=domain,
            fields=self._MESSAGE_FIELDS,
            order="date desc",
            limit=limit,
        )

    # -- Tags ----------------------------------------------------------------

    def tags(self) -> builtins.list[dict[str, Any]]:
        """List available tags for this domain.

        Returns:
            List of tag dictionaries.

        Raises:
            ValueError: If the domain has no tag model.
        """
        if self._tag_model is None:
            msg = f"No tag model defined for {self._model}"
            raise ValueError(msg)
        return self._client.search_read(
            self._tag_model,
            fields=self._TAG_FIELDS,
            order="name",
        )

    def add_tag(
        self,
        record_id: int,
        tag_id: int,
    ) -> bool:
        """Add a tag to a record (idempotent).

        Args:
            record_id: Record ID.
            tag_id: Tag ID.

        Returns:
            ``True`` on success.
        """
        record = self.get(record_id, fields=["tag_ids"])
        current_tags: builtins.list[int] = record.get("tag_ids", [])
        if tag_id not in current_tags:
            current_tags.append(tag_id)
            return self._client.write(
                self._model,
                [record_id],
                {"tag_ids": [(6, 0, current_tags)]},
            )
        return True

    # -- Attachments ---------------------------------------------------------

    def attachments(
        self,
        record_id: int,
    ) -> builtins.list[dict[str, Any]]:
        """List attachments on a record.

        Args:
            record_id: Record ID.

        Returns:
            List of attachment metadata dictionaries.
        """
        domain: builtins.list[Any] = [
            ("res_model", "=", self._model),
            ("res_id", "=", record_id),
        ]
        return self._client.search_read(
            "ir.attachment",
            domain=domain,
            fields=self._ATTACHMENT_LIST_FIELDS,
        )

    def attach(
        self,
        record_id: int,
        file_path: Path | str | None = None,
        *,
        data: bytes | None = None,
        name: str | None = None,
    ) -> int:
        """Attach a file (from disk or bytes) to a record.

        Args:
            record_id: Record ID.
            file_path: Path to file on disk (mutually exclusive with *data*).
            data: Raw bytes (mutually exclusive with *file_path*).
            name: Attachment name (defaults to filename; required with *data*).

        Returns:
            ID of the created ``ir.attachment``.

        Raises:
            ValueError: If arguments are invalid.
            FileNotFoundError: If *file_path* does not exist.
        """
        from vodoo.base import _prepare_attachment_upload

        values = _prepare_attachment_upload(file_path, data, name, self._model, record_id)
        return self._client.create("ir.attachment", values)

    def download(
        self,
        record_id: int,
        output_dir: Path | None = None,
        extension: str | None = None,
    ) -> builtins.list[Path]:
        """Download all attachments for a record to disk.

        Args:
            record_id: Record ID.
            output_dir: Target directory (default: cwd).
            extension: Filter by file extension (e.g. ``'pdf'``).

        Returns:
            List of paths to downloaded files.
        """
        import logging

        if output_dir is None:
            output_dir = Path.cwd()
        elif not output_dir.exists():
            output_dir.mkdir(parents=True, exist_ok=True)

        att_list = self.attachments(record_id)

        if extension:
            ext = extension.lower().lstrip(".")
            att_list = [a for a in att_list if a.get("name", "").lower().endswith(f".{ext}")]

        downloaded: builtins.list[Path] = []
        for att_meta in att_list:
            filename = att_meta.get("name", f"attachment_{att_meta['id']}")
            try:
                att_data = self._client.read(
                    "ir.attachment",
                    [att_meta["id"]],
                    self._ATTACHMENT_READ_FIELDS,
                )
                if not att_data:
                    continue
                att = att_data[0]
                filename = att.get("name", f"attachment_{att_meta['id']}")
                out = output_dir / filename
                if att.get("datas"):
                    out.write_bytes(base64.b64decode(att["datas"]))
                    downloaded.append(out)
            except Exception as e:
                logging.getLogger("vodoo").warning("Failed to download %s: %s", filename, e)
                continue
        return downloaded

    def attachment_data(
        self,
        attachment_id: int,
    ) -> bytes:
        """Read an attachment and return raw binary content.

        Args:
            attachment_id: Attachment ID.

        Returns:
            Raw bytes.

        Raises:
            RecordNotFoundError: If attachment not found or has no data.
        """
        from vodoo.base import _decode_attachment_data

        attachments = self._client.read(
            "ir.attachment", [attachment_id], self._ATTACHMENT_READ_FIELDS
        )
        if not attachments:
            raise RecordNotFoundError("ir.attachment", attachment_id)
        return _decode_attachment_data(attachments[0], attachment_id)

    def all_attachment_data(
        self,
        record_id: int,
    ) -> builtins.list[tuple[int, str, bytes]]:
        """Read all attachments for a record, returning in-memory data.

        Args:
            record_id: Record ID.

        Returns:
            List of ``(attachment_id, filename, raw_bytes)`` tuples.
        """
        from vodoo.base import _decode_attachment_record

        att_list = self.attachments(record_id)
        result: builtins.list[tuple[int, str, bytes]] = []
        for att_meta in att_list:
            att_id = att_meta["id"]
            try:
                att_data = self._client.read(
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
        """Return the Odoo web URL for a record.

        Args:
            record_id: Record ID.

        Returns:
            Full URL to the record form view.
        """
        base_url = self._client.config.url.rstrip("/")
        return f"{base_url}/web#id={record_id}&model={self._model}&view_type=form"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _convert_to_html(text: str, use_markdown: bool = False) -> str:
    """Convert text to HTML, optionally processing markdown."""
    if use_markdown:
        from vodoo.content import _markdown_to_html

        return _markdown_to_html(text)
    return f"<p>{text}</p>"
