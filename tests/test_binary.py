"""Tests for binary field handling utilities."""

from __future__ import annotations

import base64
from pathlib import Path

from vodoo.base import mask_binary_fields, save_binary_field


class TestMaskBinaryFields:
    """Test binary field masking in record dicts."""

    def test_masks_small_binary(self) -> None:
        data = base64.b64encode(b"hello").decode()
        records = [{"id": 1, "name": "test", "datas": data}]
        mask_binary_fields(records, {"datas"})
        assert records[0]["datas"].startswith("<binary ")
        assert records[0]["datas"].endswith(">")

    def test_masks_large_binary_kb(self) -> None:
        data = base64.b64encode(b"x" * 5000).decode()
        records = [{"id": 1, "datas": data}]
        mask_binary_fields(records, {"datas"})
        assert "KB" in records[0]["datas"]

    def test_masks_large_binary_mb(self) -> None:
        data = base64.b64encode(b"x" * 2_000_000).decode()
        records = [{"id": 1, "datas": data}]
        mask_binary_fields(records, {"datas"})
        assert "MB" in records[0]["datas"]

    def test_preserves_non_binary_fields(self) -> None:
        records = [{"id": 1, "name": "test", "datas": base64.b64encode(b"x").decode()}]
        mask_binary_fields(records, {"datas"})
        assert records[0]["name"] == "test"
        assert records[0]["id"] == 1

    def test_ignores_empty_binary(self) -> None:
        records = [{"id": 1, "datas": False}]
        mask_binary_fields(records, {"datas"})
        assert records[0]["datas"] is False

    def test_ignores_none_binary(self) -> None:
        records = [{"id": 1, "datas": None}]
        mask_binary_fields(records, {"datas"})
        assert records[0]["datas"] is None

    def test_ignores_missing_field(self) -> None:
        records = [{"id": 1, "name": "test"}]
        mask_binary_fields(records, {"datas"})
        assert "datas" not in records[0]

    def test_no_binary_fields_is_noop(self) -> None:
        records = [{"id": 1, "name": "test"}]
        original = records[0].copy()
        mask_binary_fields(records, set())
        assert records[0] == original

    def test_multiple_records(self) -> None:
        data = base64.b64encode(b"content").decode()
        records = [
            {"id": 1, "datas": data},
            {"id": 2, "datas": data},
        ]
        mask_binary_fields(records, {"datas"})
        assert all(r["datas"].startswith("<binary ") for r in records)

    def test_multiple_binary_fields(self) -> None:
        data = base64.b64encode(b"content").decode()
        records = [{"id": 1, "datas": data, "image": data}]
        mask_binary_fields(records, {"datas", "image"})
        assert records[0]["datas"].startswith("<binary ")
        assert records[0]["image"].startswith("<binary ")


class TestSaveBinaryField:
    """Test saving base64 data to a file."""

    def test_saves_to_file(self, tmp_path: Path) -> None:
        data = base64.b64encode(b"hello world").decode()
        out = tmp_path / "output.txt"
        result = save_binary_field(data, out)
        assert result.exists()
        assert result.read_bytes() == b"hello world"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        data = base64.b64encode(b"test").decode()
        out = tmp_path / "sub" / "dir" / "file.bin"
        result = save_binary_field(data, out)
        assert result.exists()
        assert result.read_bytes() == b"test"

    def test_returns_resolved_path(self, tmp_path: Path) -> None:
        data = base64.b64encode(b"x").decode()
        out = tmp_path / "file.bin"
        result = save_binary_field(data, out)
        assert result.is_absolute()
