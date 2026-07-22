"""Tests for Odoo Documents namespaces and CLI commands."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from vodoo.aio.documents import AsyncDocumentNamespace
from vodoo.documents import DocumentNamespace
from vodoo.exceptions import RecordNotFoundError, VodooError
from vodoo.main import app


class _StubClient:
    def __init__(self) -> None:
        self.search_results: list[dict[str, Any]] = []
        self.read_results: list[dict[str, Any]] = []
        self.calls: list[tuple[str, Any]] = []

    def search_read(self, model: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("search_read", (model, kwargs)))
        return self.search_results

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        self.calls.append(("create", (model, values, context)))
        return 42

    def read(
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        self.calls.append(("read", (model, ids, fields)))
        return self.read_results


class _StubAsyncClient(_StubClient):
    async def search_read(self, model: str, **kwargs: Any) -> list[dict[str, Any]]:  # type: ignore[override]
        return super().search_read(model, **kwargs)

    async def create(  # type: ignore[override]
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        return super().create(model, values, context)

    async def read(  # type: ignore[override]
        self, model: str, ids: list[int], fields: list[str] | None = None
    ) -> list[dict[str, Any]]:
        return super().read(model, ids, fields)


def test_upload_resolves_folder_name_and_encodes_file(tmp_path: Path) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"pdf contents")
    client = _StubClient()
    client.search_results = [{"id": 1536, "name": "Finanzen Semadox"}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    document_id = documents.upload(path, folder="Finanzen Semadox")

    assert document_id == 42
    _, (model, values, context) = client.calls[-1]
    assert model == "documents.document"
    assert context is None
    assert values == {
        "name": "invoice.pdf",
        "folder_id": 1536,
        "datas": base64.b64encode(b"pdf contents").decode("ascii"),
    }


def test_upload_accepts_numeric_folder_and_custom_name(tmp_path: Path) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"data")
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    documents.upload(path, folder="1536", name="vendor-invoice.pdf")

    assert all(call[0] != "search_read" for call in client.calls)
    _, (_, values, _) = client.calls[-1]
    assert values["folder_id"] == 1536
    assert values["name"] == "vendor-invoice.pdf"


def test_resolve_folder_rejects_missing_and_ambiguous_names() -> None:
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    with pytest.raises(VodooError, match="folder not found"):
        documents.resolve_folder("Missing")

    client.search_results = [{"id": 1}, {"id": 2}]
    with pytest.raises(VodooError, match="Multiple document folders"):
        documents.resolve_folder("Invoices")


def test_folders_filters_folder_records() -> None:
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    documents.folders(limit=10)

    _, (model, kwargs) = client.calls[-1]
    assert model == "documents.document"
    assert kwargs["domain"] == [("type", "=", "folder")]
    assert kwargs["limit"] == 10


def test_download_decodes_data_and_uses_document_name(tmp_path: Path) -> None:
    client = _StubClient()
    client.read_results = [
        {"id": 7, "name": "invoice.pdf", "datas": base64.b64encode(b"contents").decode()}
    ]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(7, tmp_path)

    assert output == (tmp_path / "invoice.pdf").resolve()
    assert output.read_bytes() == b"contents"


def test_download_missing_document_raises() -> None:
    documents = DocumentNamespace(_StubClient())  # type: ignore[arg-type]
    with pytest.raises(RecordNotFoundError):
        documents.download_file(404)


def test_async_upload_and_download(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"async data")
    client = _StubAsyncClient()
    client.search_results = [{"id": 9, "name": "Inbox"}]
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    document_id = asyncio.run(documents.upload(source, folder="Inbox"))
    client.read_results = [
        {"name": "download.txt", "datas": base64.b64encode(b"downloaded").decode()}
    ]
    output = asyncio.run(documents.download_file(document_id, tmp_path / "output.txt"))

    assert document_id == 42
    assert output.read_bytes() == b"downloaded"


def test_document_cli_exposes_suggested_commands() -> None:
    result = CliRunner().invoke(app, ["document", "--help"])

    assert result.exit_code == 0
    for command in ("upload", "list", "download", "folders"):
        assert command in result.output


def test_document_upload_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"data")

    class _Documents:
        def upload(self, file_path: Path, *, folder: str, name: str | None) -> int:
            assert file_path == source
            assert folder == "Finanzen Semadox"
            assert name is None
            return 88

    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=_Documents()))
    result = CliRunner().invoke(
        app, ["document", "upload", str(source), "--folder", "Finanzen Semadox"]
    )

    assert result.exit_code == 0
    assert "Successfully uploaded" in result.output
    assert "88" in result.output
