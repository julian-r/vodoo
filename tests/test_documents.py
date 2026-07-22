"""Tests for Odoo Documents namespaces and CLI commands."""

from __future__ import annotations

import asyncio
import base64
import json
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
        self.fields_result: dict[str, Any] = {"folder_id": {"relation": "documents.document"}}
        self.calls: list[tuple[str, Any]] = []

    def fields_get(
        self,
        model: str,
        fields: list[str] | None = None,
        attributes: list[str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("fields_get", (model, fields, attributes)))
        return self.fields_result

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
    async def fields_get(  # type: ignore[override]
        self,
        model: str,
        fields: list[str] | None = None,
        attributes: list[str] | None = None,
    ) -> dict[str, Any]:
        return super().fields_get(model, fields, attributes)

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


@pytest.mark.parametrize(
    ("folder_model", "expected_domain"),
    [
        ("documents.folder", []),
        ("documents.document", [("type", "=", "folder")]),
    ],
)
def test_folders_supports_old_and_new_schemas(
    folder_model: str, expected_domain: list[Any]
) -> None:
    client = _StubClient()
    client.fields_result = {"folder_id": {"relation": folder_model}}
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    documents.folders(limit=10)

    assert client.calls[0] == (
        "fields_get",
        ("documents.document", ["folder_id"], ["relation"]),
    )
    _, (model, kwargs) = client.calls[-1]
    assert model == folder_model
    assert kwargs["domain"] == expected_domain
    assert kwargs["limit"] == 10


def test_resolve_folder_uses_legacy_folder_model() -> None:
    client = _StubClient()
    client.fields_result = {"folder_id": {"relation": "documents.folder"}}
    client.search_results = [{"id": 12, "name": "Invoices"}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    assert documents.resolve_folder("Invoices") == 12
    _, (model, kwargs) = client.calls[-1]
    assert model == "documents.folder"
    assert kwargs["domain"] == [("name", "=", "Invoices")]


def test_download_decodes_data_and_uses_document_name(tmp_path: Path) -> None:
    client = _StubClient()
    client.read_results = [
        {"id": 7, "name": "invoice.pdf", "datas": base64.b64encode(b"contents").decode()}
    ]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(7, tmp_path)

    assert output == (tmp_path / "invoice.pdf").resolve()
    assert output.read_bytes() == b"contents"


def test_download_sanitizes_remote_name(tmp_path: Path) -> None:
    client = _StubClient()
    client.read_results = [{"name": "../outside.txt", "datas": base64.b64encode(b"safe").decode()}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(7, tmp_path)

    assert output == (tmp_path / "outside.txt").resolve()
    assert output.read_bytes() == b"safe"


def test_download_allows_empty_binary_data(tmp_path: Path) -> None:
    client = _StubClient()
    client.read_results = [{"name": "empty.txt", "datas": ""}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(8, tmp_path)

    assert output.read_bytes() == b""


def test_download_missing_document_or_data_raises() -> None:
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]
    with pytest.raises(RecordNotFoundError):
        documents.download_file(404)

    client.read_results = [{"name": "link"}]
    with pytest.raises(RecordNotFoundError):
        documents.download_file(405)


def test_async_upload_and_download(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"async data")
    client = _StubAsyncClient()
    client.search_results = [{"id": 9, "name": "Inbox"}]
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    document_id = asyncio.run(documents.upload(source, folder="Inbox"))
    client.read_results = [
        {"name": "../download.txt", "datas": base64.b64encode(b"downloaded").decode()}
    ]
    output = asyncio.run(documents.download_file(document_id, tmp_path))

    assert document_id == 42
    assert output == (tmp_path / "download.txt").resolve()
    assert output.read_bytes() == b"downloaded"


def test_async_folders_supports_legacy_schema() -> None:
    client = _StubAsyncClient()
    client.fields_result = {"folder_id": {"relation": "documents.folder"}}
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    asyncio.run(documents.folders())

    _, (model, kwargs) = client.calls[-1]
    assert model == "documents.folder"
    assert kwargs["domain"] == []


def test_async_download_allows_empty_binary_data(tmp_path: Path) -> None:
    client = _StubAsyncClient()
    client.read_results = [{"name": "empty.txt", "datas": ""}]
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    output = asyncio.run(documents.download_file(8, tmp_path))

    assert output.read_bytes() == b""


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


def test_document_upload_cli_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"data")

    class _Documents:
        def upload(self, file_path: Path, *, folder: str, name: str | None) -> int:
            assert file_path == source
            assert folder == "12"
            assert name == "custom.pdf"
            return 89

    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=_Documents()))
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "document",
            "upload",
            str(source),
            "--folder",
            "12",
            "--name",
            "custom.pdf",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {"ok": True, "id": 89, "name": "custom.pdf"}
