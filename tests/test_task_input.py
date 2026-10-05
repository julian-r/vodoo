"""Verbatim description loading, before any client I/O."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from vodoo.cli.task_input import load_description
from vodoo.exceptions import FieldParsingError


def test_inline_and_omitted_input() -> None:
    assert load_description(None, None) is None
    assert load_description("", None) == ""
    assert load_description("  ü\n", None) == "  ü\n"


def test_utf8_file_preserves_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "task.md"
    content = "  # Grüße 世界 🚀\r\n\r\n  * détail *  \n"
    path.write_bytes(content.encode("utf-8"))
    assert load_description(None, path) == content
    path.write_bytes(b"")
    assert load_description(None, path) == ""


def test_stdin_utf8_ignores_stream_encoding(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.TextIOWrapper(io.BytesIO("  Grüße 世界\r\n".encode()), encoding="ascii")
    monkeypatch.setattr("sys.stdin", stream)
    assert load_description(None, Path("-")) == "  Grüße 世界\r\n"


def test_text_only_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("  Grüße\n"))
    assert load_description(None, Path("-")) == "  Grüße\n"


def test_invalid_utf8_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = io.TextIOWrapper(io.BytesIO(b"\xff"), encoding="utf-8")
    monkeypatch.setattr("sys.stdin", stream)
    with pytest.raises(FieldParsingError, match="UTF-8"):
        load_description(None, Path("-"))


@pytest.mark.parametrize("inline", ["", "text"])
@pytest.mark.parametrize("path", [Path("missing.md"), Path("-")])
def test_conflict_precedes_read(inline: str, path: Path) -> None:
    with pytest.raises(FieldParsingError, match="mutually exclusive"):
        load_description(inline, path)


def test_missing_directory_invalid_utf8(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.md"
    invalid.write_bytes(b"\xff")
    for path in (tmp_path / "missing.md", tmp_path, invalid):
        with pytest.raises(FieldParsingError, match="Cannot read UTF-8 description"):
            load_description(None, path)


def test_unreadable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def unreadable(_path: Path) -> bytes:
        raise PermissionError("permission denied")

    monkeypatch.setattr(Path, "read_bytes", unreadable)
    with pytest.raises(FieldParsingError, match="permission denied"):
        load_description(None, tmp_path / "task.md")
