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
from vodoo.documents import DocumentNamespace, _order_folder_tree, _prepare_document_values
from vodoo.exceptions import RecordNotFoundError, VodooError
from vodoo.main import app


class _StubClient:
    def __init__(self) -> None:
        self.search_results: list[dict[str, Any]] = []
        self.read_results: list[dict[str, Any]] = []
        self.config = SimpleNamespace(url="https://odoo.example.com/")
        self.fields_result: dict[str, Any] = {
            "type": {"selection": [["binary", "File"], ["folder", "Folder"]]}
        }
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

    result = documents.upload(path, folder="Finanzen Semadox")

    assert result == 42
    _, (model, values, context) = client.calls[-1]
    assert model == "documents.document"
    assert context is None
    assert values == {
        "name": "invoice.pdf",
        "folder_id": 1536,
        "datas": base64.b64encode(b"pdf contents").decode("ascii"),
        "mimetype": "application/pdf",
    }


@pytest.mark.parametrize(
    ("selector", "value"), [("folder", 1536), ("folder", "1536"), ("folder_id", 1536)]
)
def test_upload_accepts_numeric_folder_and_custom_name(
    tmp_path: Path, selector: str, value: int | str
) -> None:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(b"data")
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    result = documents.upload(path, **{selector: value}, name="vendor-invoice.pdf")

    assert result == 42
    assert all(call[0] not in {"search_read", "fields_get"} for call in client.calls)
    _, (_, values, _) = client.calls[-1]
    assert values["folder_id"] == 1536
    assert values["name"] == "vendor-invoice.pdf"


def test_resolve_folder_rejects_missing_and_ambiguous_names() -> None:
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    with pytest.raises(VodooError, match=r"No documents\.document"):
        documents.resolve_folder("Missing")

    client.search_results = [{"id": 1}, {"id": 2}]
    with pytest.raises(VodooError, match=r"Multiple documents\.document"):
        documents.resolve_folder("Invoices")


@pytest.mark.parametrize(
    ("modern", "folder_model", "expected_domain"),
    [
        (False, "documents.folder", []),
        (True, "documents.document", [("type", "=", "folder")]),
    ],
)
def test_folders_supports_old_and_new_schemas(
    modern: bool, folder_model: str, expected_domain: list[Any]
) -> None:
    client = _StubClient()
    client.fields_result = {
        "type": {"selection": [["binary", "File"], ["folder", "Folder"]] if modern else []}
    }
    client.search_results = [{"id": 2, "name": "Invoices", "folder_id": [1, "Finance"]}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    folders = documents.folders(10)

    assert client.calls[0] == (
        "fields_get",
        ("documents.document", ["type"], ["selection"]),
    )
    _, (model, kwargs) = client.calls[-1]
    assert model == folder_model
    assert kwargs["domain"] == expected_domain
    assert kwargs["limit"] == 10
    if modern:
        assert folders[0]["parent_folder_id"] == [1, "Finance"]
        assert "folder_id" not in folders[0]


def test_resolve_folder_uses_legacy_folder_model() -> None:
    client = _StubClient()
    client.fields_result = {"type": {"selection": []}}
    client.search_results = [{"id": 12, "name": "Invoices"}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    assert documents.resolve_folder("Invoices") == 12
    _, (model, kwargs) = client.calls[-1]
    assert model == "documents.folder"
    assert kwargs["domain"] == [("name", "=", "Invoices")]


def test_folder_tree_orders_children_and_adds_paths() -> None:
    folders = [
        {"id": 3, "name": "Invoices", "parent_folder_id": [1, "Finance"]},
        {"id": 2, "name": "HR", "parent_folder_id": False},
        {"id": 1, "name": "Finance", "parent_folder_id": False},
    ]

    result = _order_folder_tree(folders)

    assert [(item["id"], item["depth"], item["path"]) for item in result] == [
        (1, 0, "Finance"),
        (3, 1, "Finance / Invoices"),
        (2, 0, "HR"),
    ]


def test_upload_by_ids_sets_mimetype_tags_owner_and_url(tmp_path: Path) -> None:
    path = tmp_path / "report.pdf"
    path.write_bytes(b"report")
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    result = documents.upload(
        path,
        folder_id=3,
        tags=[8, "9"],
        owner=12,
        name="Protocol.pdf",
    )

    assert result == 42
    assert all(call[0] not in {"fields_get", "search_read"} for call in client.calls)
    _, (_, values, _) = client.calls[-1]
    assert values == {
        "name": "Protocol.pdf",
        "datas": base64.b64encode(b"report").decode("ascii"),
        "mimetype": "application/pdf",
        "folder_id": 3,
        "tag_ids": [(6, 0, [8, 9])],
        "owner_id": 12,
    }


@pytest.mark.parametrize(("folder", "folder_id"), [(None, None), ("Finance", 3), (None, 0)])
def test_upload_rejects_invalid_folder_selector(
    tmp_path: Path, folder: str | None, folder_id: int | None
) -> None:
    documents = DocumentNamespace(_StubClient())  # type: ignore[arg-type]

    with pytest.raises(VodooError):
        documents.upload(tmp_path / "unused", folder=folder, folder_id=folder_id)


def test_prepare_values_unknown_mimetype_falls_back_to_binary(tmp_path: Path) -> None:
    path = tmp_path / "file.vodoo-unknown-extension"
    path.write_bytes(b"hello")

    values = _prepare_document_values(path, folder_id=3)

    assert values["mimetype"] == "application/octet-stream"


def test_download_decodes_data_and_uses_document_name(tmp_path: Path) -> None:
    client = _StubClient()
    client.read_results = [
        {"id": 7, "name": "invoice.pdf", "datas": base64.b64encode(b"contents").decode()}
    ]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(7, tmp_path)

    assert output == (tmp_path / "invoice.pdf").resolve()
    assert output.read_bytes() == b"contents"


@pytest.mark.parametrize(
    ("remote_name", "safe_name"),
    [
        ("../outside.txt", "outside.txt"),
        (r"C:\\drive.txt", "drive.txt"),
        ("C:drive.txt", "C_drive.txt"),
        ("report.txt:alternate", "report.txt_alternate"),
        ("CON", "_CON"),
    ],
)
def test_download_sanitizes_remote_name(tmp_path: Path, remote_name: str, safe_name: str) -> None:
    client = _StubClient()
    client.read_results = [{"name": remote_name, "datas": base64.b64encode(b"safe").decode()}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(7, tmp_path)

    assert output == (tmp_path / safe_name).resolve()
    assert output.read_bytes() == b"safe"


def test_download_allows_empty_binary_data(tmp_path: Path) -> None:
    client = _StubClient()
    client.read_results = [{"name": "empty.txt", "datas": ""}]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(8, tmp_path)

    assert output.read_bytes() == b""


@pytest.mark.parametrize("normalized_data", [None, False])
def test_download_allows_normalized_empty_binary_data(
    tmp_path: Path, normalized_data: None | bool
) -> None:
    client = _StubClient()
    client.read_results = [
        {
            "name": "empty.txt",
            "type": "binary",
            "file_size": 0,
            "datas": normalized_data,
        }
    ]
    documents = DocumentNamespace(client)  # type: ignore[arg-type]

    output = documents.download_file(8, tmp_path)

    assert output.read_bytes() == b""
    _, (_, _, fields) = client.calls[-1]
    assert fields == ["name", "type", "file_size", "datas"]


def test_download_missing_document_or_data_raises() -> None:
    client = _StubClient()
    documents = DocumentNamespace(client)  # type: ignore[arg-type]
    with pytest.raises(RecordNotFoundError):
        documents.download_file(404)

    for document in (
        {"name": "folder", "type": "folder", "file_size": 0, "datas": None},
        {"name": "link", "type": "url", "file_size": 0, "datas": None},
        {"name": "missing.pdf", "type": "binary", "file_size": 10, "datas": None},
    ):
        client.read_results = [document]
        with pytest.raises(RecordNotFoundError):
            documents.download_file(405)


def test_async_upload_and_download(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"async data")
    client = _StubAsyncClient()
    client.search_results = [{"id": 9, "name": "Inbox"}]
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    result = asyncio.run(documents.upload(source, folder="Inbox"))
    client.read_results = [
        {"name": "../download.txt", "datas": base64.b64encode(b"downloaded").decode()}
    ]
    output = asyncio.run(documents.download_file(result, tmp_path))

    assert result == 42
    assert output == (tmp_path / "download.txt").resolve()
    assert output.read_bytes() == b"downloaded"


def test_async_folders_supports_legacy_schema() -> None:
    client = _StubAsyncClient()
    client.fields_result = {"type": {"selection": []}}
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    asyncio.run(documents.folders(17))

    _, (model, kwargs) = client.calls[-1]
    assert model == "documents.folder"
    assert kwargs["domain"] == []
    assert kwargs["limit"] == 17


def test_async_upload_accepts_numeric_string_folder(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_bytes(b"async data")
    client = _StubAsyncClient()
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    result = asyncio.run(documents.upload(source, folder="1536"))

    assert result == 42
    assert all(call[0] not in {"search_read", "fields_get"} for call in client.calls)
    _, (_, values, _) = client.calls[-1]
    assert values["folder_id"] == 1536


@pytest.mark.parametrize("normalized_data", [None, False])
def test_async_download_allows_normalized_empty_binary_data(
    tmp_path: Path, normalized_data: None | bool
) -> None:
    client = _StubAsyncClient()
    client.read_results = [
        {
            "name": "empty.txt",
            "type": "binary",
            "file_size": 0,
            "datas": normalized_data,
        }
    ]
    documents = AsyncDocumentNamespace(client)  # type: ignore[arg-type]

    output = asyncio.run(documents.download_file(8, tmp_path))

    assert output.read_bytes() == b""


def test_document_cli_exposes_suggested_commands() -> None:
    result = CliRunner().invoke(app, ["document", "--help"])

    assert result.exit_code == 0
    for command in ("upload", "list", "download", "folders"):
        assert command in result.output


def test_document_folders_tree_cli_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Documents:
        def folders(self, *, tree: bool, limit: int) -> list[dict[str, Any]]:
            assert tree is True
            assert limit == 7
            return [{"id": 2, "name": "Invoices", "depth": 1, "path": "Finance / Invoices"}]

    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=_Documents()))

    result = CliRunner().invoke(app, ["--json", "document", "folders", "--tree", "--limit", "7"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [
        {"id": 2, "name": "Invoices", "depth": 1, "path": "Finance / Invoices"}
    ]


def test_document_upload_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"data")

    class _Documents:
        def upload(self, file_path: Path, **options: Any) -> int:
            assert file_path == source
            assert options == {
                "folder": "Finanzen Semadox",
                "folder_id": None,
                "tags": None,
                "owner": None,
                "name": None,
            }
            return 88

        def url(self, document_id: int) -> str:
            assert document_id == 88
            return "https://odoo.example.com/document/88"

    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=_Documents()))
    result = CliRunner().invoke(
        app, ["--simple", "document", "upload", str(source), "--folder", "Finanzen Semadox"]
    )

    assert result.exit_code == 0
    assert "Successfully uploaded" in result.output
    assert "88" in result.output


def test_document_upload_cli_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source = tmp_path / "invoice.pdf"
    source.write_bytes(b"data")

    class _Documents:
        def upload(self, file_path: Path, **options: Any) -> int:
            assert file_path == source
            assert options == {
                "folder": None,
                "folder_id": 12,
                "tags": ["Approved", "9"],
                "owner": "audit@example.com",
                "name": "custom.pdf",
            }
            return 89

        def url(self, document_id: int) -> str:
            assert document_id == 89
            return "https://odoo.example.com/document/89"

    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=_Documents()))
    result = CliRunner().invoke(
        app,
        [
            "--json",
            "document",
            "upload",
            str(source),
            "--folder-id",
            "12",
            "--tag",
            "Approved",
            "--tag",
            "9",
            "--owner",
            "audit@example.com",
            "--name",
            "custom.pdf",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output) == {
        "ok": True,
        "id": 89,
        "name": "custom.pdf",
        "url": "https://odoo.example.com/document/89",
    }


def test_document_cli_json_delegates_list_folders_and_download(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    class _Documents:
        def __init__(self) -> None:
            self.calls: list[tuple[str, Any]] = []

        def resolve_folder(self, folder: str) -> int:
            self.calls.append(("resolve_folder", folder))
            return 12

        def list(self, *, domain: list[Any], limit: int) -> list[dict[str, Any]]:
            self.calls.append(("list", (domain, limit)))
            return [{"id": 4, "name": "invoice.pdf"}]

        def folders(self, *, tree: bool, limit: int) -> list[dict[str, Any]]:
            self.calls.append(("folders", (tree, limit)))
            return [{"id": 12, "name": "Invoices"}]

        def download_file(self, document_id: int, output: Path | None) -> Path:
            self.calls.append(("download_file", (document_id, output)))
            return tmp_path / "invoice.pdf"

    documents = _Documents()
    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=documents))
    runner = CliRunner()

    list_result = runner.invoke(
        app,
        ["--json", "document", "list", "--folder", "Invoices", "--limit", "2"],
    )
    folders_result = runner.invoke(app, ["--json", "document", "folders", "--limit", "3"])
    output = tmp_path / "custom.pdf"
    download_result = runner.invoke(
        app,
        ["--json", "document", "download", "4", "--output", str(output)],
    )

    assert list_result.exit_code == 0
    assert json.loads(list_result.output) == [{"id": 4, "name": "invoice.pdf"}]
    assert folders_result.exit_code == 0
    assert json.loads(folders_result.output) == [{"id": 12, "name": "Invoices"}]
    assert download_result.exit_code == 0
    assert json.loads(download_result.output) == {
        "ok": True,
        "id": 4,
        "path": str(tmp_path / "invoice.pdf"),
    }
    assert documents.calls == [
        ("resolve_folder", "Invoices"),
        ("list", ([("type", "=", "binary"), ("folder_id", "=", 12)], 2)),
        ("folders", (False, 3)),
        ("download_file", (4, output)),
    ]


def test_document_cli_json_reports_vodoo_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Documents:
        def list(self, *, domain: list[Any], limit: int) -> list[dict[str, Any]]:
            del domain, limit
            raise VodooError("Documents unavailable")

    monkeypatch.setattr("vodoo.main.get_client", lambda: SimpleNamespace(documents=_Documents()))
    result = CliRunner().invoke(app, ["--json", "document", "list"])

    assert result.exit_code == 1
    assert json.loads(result.output) == {
        "error": "Documents unavailable",
        "type": "vodoo_error",
    }
