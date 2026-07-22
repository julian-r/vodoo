"""Tests for --json output mode infrastructure."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

import pytest
import typer

from vodoo.base import (
    configure_output,
    display_record_detail,
    display_records,
    is_json_output,
    json_print,
)


class TestJsonOutputConfig:
    """Test that JSON mode can be enabled/disabled."""

    def setup_method(self) -> None:
        configure_output(json_mode=False)

    def teardown_method(self) -> None:
        configure_output(json_mode=False)

    def test_json_mode_off_by_default(self) -> None:
        configure_output()
        assert is_json_output() is False

    def test_json_mode_can_be_enabled(self) -> None:
        configure_output(json_mode=True)
        assert is_json_output() is True

    def test_json_mode_can_be_disabled(self) -> None:
        configure_output(json_mode=True)
        configure_output(json_mode=False)
        assert is_json_output() is False


class TestJsonPrint:
    """Test json_print outputs valid JSON."""

    def test_prints_dict(self, capsys: Any) -> None:
        json_print({"ok": True, "id": 42})
        captured = capsys.readouterr()
        assert json.loads(captured.out) == {"ok": True, "id": 42}

    def test_prints_list(self, capsys: Any) -> None:
        json_print([{"id": 1}, {"id": 2}])
        captured = capsys.readouterr()
        assert json.loads(captured.out) == [{"id": 1}, {"id": 2}]

    def test_prints_empty_list(self, capsys: Any) -> None:
        json_print([])
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []

    def test_handles_non_serializable_with_default_str(self, capsys: Any) -> None:
        from datetime import date

        json_print({"date": date(2026, 1, 1)})
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["date"] == "2026-01-01"


class TestDisplayRecordsJson:
    """Test display_records in JSON mode."""

    def setup_method(self) -> None:
        configure_output(json_mode=True)

    def teardown_method(self) -> None:
        configure_output(json_mode=False)

    def test_outputs_json_array(self, capsys: Any) -> None:
        records = [
            {"id": 1, "name": "Ticket A", "stage_id": [3, "Open"]},
            {"id": 2, "name": "Ticket B", "stage_id": [4, "Done"]},
        ]
        display_records(records, title="Tickets")
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[0]["stage_id"] == [3, "Open"]

    def test_empty_records_outputs_empty_array(self, capsys: Any) -> None:
        display_records([], title="Empty")
        captured = capsys.readouterr()
        assert json.loads(captured.out) == []

    def test_preserves_raw_values(self, capsys: Any) -> None:
        """JSON mode outputs raw Odoo values — no formatting."""
        records = [{"id": 1, "user_id": [5, "Admin"], "tag_ids": [1, 2, 3]}]
        display_records(records)
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result[0]["user_id"] == [5, "Admin"]
        assert result[0]["tag_ids"] == [1, 2, 3]


class TestDisplayRecordDetailJson:
    """Test display_record_detail in JSON mode."""

    def setup_method(self) -> None:
        configure_output(json_mode=True)

    def teardown_method(self) -> None:
        configure_output(json_mode=False)

    def test_outputs_json_object(self, capsys: Any) -> None:
        record = {
            "id": 42,
            "name": "Fix login bug",
            "stage_id": [3, "In Progress"],
            "user_id": [5, "Admin"],
            "description": "<p>Details</p>",
        }
        display_record_detail(record, record_type="Task")
        captured = capsys.readouterr()
        result = json.loads(captured.out)
        assert result["id"] == 42
        assert result["name"] == "Fix login bug"
        assert result["stage_id"] == [3, "In Progress"]
        assert result["description"] == "<p>Details</p>"


class TestStructuredErrorFallback:
    """Test errors remain visible when the active formatter is broken."""

    def test_broken_toon_formatter_falls_back_to_json_stderr(self, capsys: Any) -> None:
        from vodoo import main

        configure_output(json_mode=False, toon_mode=True)
        try:
            with (
                patch(
                    "vodoo.main.structured_print",
                    side_effect=NotImplementedError("TOON encoder is not yet implemented"),
                ) as formatter,
                pytest.raises(typer.Exit) as exc_info,
                main._handle_errors(),
            ):
                main.structured_print({"ok": True})
        finally:
            configure_output(json_mode=False, toon_mode=False)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert json.loads(captured.err) == {
            "error": "TOON encoder is not yet implemented",
            "type": "unexpected",
        }
        assert formatter.call_count == 2
        assert exc_info.value.exit_code == 1
        assert isinstance(exc_info.value.__cause__, NotImplementedError)


class TestMutualExclusivity:
    """Test --simple and --json cannot be used together."""

    def test_simple_and_json_raises(self) -> None:
        from typer.testing import CliRunner

        from vodoo.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["--simple", "--json", "helpdesk", "list"])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output.lower() or result.exit_code != 0
