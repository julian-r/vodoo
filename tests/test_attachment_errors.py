"""Bulk attachment operations must not hide permission or download failures."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo import base
from vodoo.aio import base as async_base
from vodoo.aio.project_tasks import AsyncTaskNamespace
from vodoo.exceptions import OdooAccessError, TransportError
from vodoo.project_tasks import TaskNamespace


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("operation", ["namespace", "helper", "download"])
@pytest.mark.parametrize("failure", ["access", "transport", "decode"])
def test_bulk_failure_propagates_after_a_readable_attachment(
    asynchronous: bool, operation: str, failure: str, tmp_path: Path
) -> None:
    client = MagicMock()
    metadata = [{"id": 1, "name": "one.txt"}, {"id": 2, "name": "two.txt"}]
    first = [{"id": 1, "name": "one.txt", "datas": base64.b64encode(b"one").decode()}]
    error = (
        OdooAccessError("Attachment read denied", code=403)
        if failure == "access"
        else TransportError("Attachment read failed")
    )
    second = [{"id": 2, "name": "two.txt", "datas": "a"}] if failure == "decode" else error
    if asynchronous:
        client.search_read = AsyncMock(return_value=metadata)
        client.read = AsyncMock(side_effect=[first, second])
        namespace = AsyncTaskNamespace(client)
        call = (
            namespace.all_attachment_data(42)
            if operation == "namespace"
            else async_base.get_record_attachment_data(client, "project.task", 42)
            if operation == "helper"
            else async_base.download_record_attachments(client, "project.task", 42, tmp_path)
        )

        def invoke() -> Any:
            return asyncio.run(call)
    else:
        client.search_read.return_value = metadata
        client.read.side_effect = [first, second]
        namespace = TaskNamespace(client)

        def invoke() -> Any:
            if operation == "namespace":
                return namespace.all_attachment_data(42)
            if operation == "helper":
                return base.get_record_attachment_data(client, "project.task", 42)
            return base.download_record_attachments(client, "project.task", 42, tmp_path)

    expected = binascii.Error if failure == "decode" else type(error)
    with pytest.raises(expected) as caught:
        invoke()
    if failure != "decode":
        assert caught.value is error
    if operation == "download":
        # Fail-fast is not an atomic download; prior successful files remain.
        assert (tmp_path / "one.txt").read_bytes() == b"one"
        assert not (tmp_path / "two.txt").exists()


@pytest.mark.parametrize("asynchronous", [False, True])
def test_filesystem_failure_propagates(
    asynchronous: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = MagicMock()
    metadata = [{"id": 1, "name": "one.txt"}]
    records = [{"name": "one.txt", "datas": "b25l"}]
    error = PermissionError("Cannot write download")

    def denied_write(_path: Path, _data: bytes) -> int:
        raise error

    monkeypatch.setattr(Path, "write_bytes", denied_write)
    if asynchronous:
        client.search_read = AsyncMock(return_value=metadata)
        client.read = AsyncMock(return_value=records)

        def invoke() -> list[Path]:
            return asyncio.run(
                async_base.download_record_attachments(client, "project.task", 42, tmp_path)
            )
    else:
        client.search_read.return_value = metadata
        client.read.return_value = records

        def invoke() -> list[Path]:
            return base.download_record_attachments(client, "project.task", 42, tmp_path)

    with pytest.raises(PermissionError) as caught:
        invoke()
    assert caught.value is error


@pytest.mark.parametrize("asynchronous", [False, True])
def test_filtered_download_never_reads_excluded_attachment(
    asynchronous: bool, tmp_path: Path
) -> None:
    client = MagicMock()
    metadata = [{"id": 1, "name": "restricted.bin"}, {"id": 2, "name": "safe.TXT"}]
    records = [{"name": "safe.TXT", "datas": "b25l"}]
    if asynchronous:
        client.search_read = AsyncMock(return_value=metadata)
        client.read = AsyncMock(return_value=records)
        result = asyncio.run(
            async_base.download_record_attachments(
                client, "project.task", 42, tmp_path, extension=".txt"
            )
        )
    else:
        client.search_read.return_value = metadata
        client.read.return_value = records
        result = base.download_record_attachments(
            client, "project.task", 42, tmp_path, extension=".txt"
        )
    assert result == [tmp_path / "safe.TXT"]
    assert client.read.call_args.args[1] == [2]
    assert client.read.call_count == 1


@pytest.mark.parametrize("has_attachment", [False, True])
def test_cli_does_not_report_success_for_denied_download(
    has_attachment: bool, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = MagicMock()
    client.search_read.return_value = [{"id": 1, "name": "one.txt"}] if has_attachment else []
    client.read.side_effect = OdooAccessError("Attachment read denied", code=403)
    client.tasks = TaskNamespace(client)
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    try:
        result = CliRunner().invoke(
            main_module.app,
            ["--json", "project-task", "download-all", "42", "--output", str(tmp_path)],
        )
        payload = json.loads(result.stdout)
        if has_attachment:
            assert result.exit_code == 1
            assert payload["type"] == "access_denied"
            assert "ok" not in payload
        else:
            assert result.exit_code == 0
            assert payload == {"ok": True, "id": 42, "files": []}
    finally:
        main_module._console_config.update(simple=False, json=False, toon=False)
        base.configure_output()
