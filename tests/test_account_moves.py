"""Tests for account.move helpers and attachment download delegation."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, ClassVar

import pytest

from vodoo._domain import DomainNamespace
from vodoo.account_moves import build_account_move_domain
from vodoo.aio._domain import AsyncDomainNamespace


class _DummyNamespace(DomainNamespace):
    _model: ClassVar[str] = "x.test.model"
    _default_fields: ClassVar[list[str]] = ["id"]


class _AsyncDummyNamespace(AsyncDomainNamespace):
    _model: ClassVar[str] = "x.test.model"
    _default_fields: ClassVar[list[str]] = ["id"]


class TestAccountMoveDomain:
    def test_empty_domain(self) -> None:
        assert build_account_move_domain() == []

    def test_domain_with_search_and_filters(self) -> None:
        domain = build_account_move_domain(
            search="INV",
            company="Rath",
            company_id=2,
            partner="Acme",
            move_type="out_invoice",
            state="posted",
            year=2025,
        )

        # 4 search fields -> 3 OR operators
        assert domain[:3] == ["|", "|", "|"]
        assert ("name", "ilike", "INV") in domain
        assert ("ref", "ilike", "INV") in domain
        assert ("company_id.name", "ilike", "Rath") in domain
        assert ("company_id", "=", 2) in domain
        assert ("partner_id.name", "ilike", "Acme") in domain
        assert ("move_type", "=", "out_invoice") in domain
        assert ("state", "=", "posted") in domain
        assert ("date", ">=", "2025-01-01") in domain
        assert ("date", "<=", "2025-12-31") in domain


class TestAttachmentDownloadDelegation:
    def test_sync_domain_download_delegates_to_base(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, Any] = {}

        def fake_download_record_attachments(
            client: Any,
            model: str,
            record_id: int,
            output_dir: Path | None = None,
            extension: str | None = None,
        ) -> list[Path]:
            captured["client"] = client
            captured["model"] = model
            captured["record_id"] = record_id
            captured["output_dir"] = output_dir
            captured["extension"] = extension
            return [Path("/tmp/test.pdf")]

        monkeypatch.setattr(
            "vodoo.base.download_record_attachments",
            fake_download_record_attachments,
        )

        client = object()
        namespace = _DummyNamespace(client=client)  # type: ignore[arg-type]
        result = namespace.download(42, Path("/tmp"), extension="pdf")

        assert result == [Path("/tmp/test.pdf")]
        assert captured["client"] is client
        assert captured["model"] == "x.test.model"
        assert captured["record_id"] == 42
        assert captured["output_dir"] == Path("/tmp")
        assert captured["extension"] == "pdf"

    def test_async_domain_download_delegates_to_aio_base(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        captured: dict[str, Any] = {}

        async def fake_download_record_attachments(
            client: Any,
            model: str,
            record_id: int,
            output_dir: Path | None = None,
            extension: str | None = None,
        ) -> list[Path]:
            captured["client"] = client
            captured["model"] = model
            captured["record_id"] = record_id
            captured["output_dir"] = output_dir
            captured["extension"] = extension
            return [Path("/tmp/test-async.pdf")]

        monkeypatch.setattr(
            "vodoo.aio.base.download_record_attachments",
            fake_download_record_attachments,
        )

        client = object()
        namespace = _AsyncDummyNamespace(client=client)  # type: ignore[arg-type]
        result = asyncio.run(namespace.download(77, Path("/tmp"), extension="pdf"))

        assert result == [Path("/tmp/test-async.pdf")]
        assert captured["client"] is client
        assert captured["model"] == "x.test.model"
        assert captured["record_id"] == 77
        assert captured["output_dir"] == Path("/tmp")
        assert captured["extension"] == "pdf"
