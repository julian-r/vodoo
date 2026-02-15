"""Unit tests for timer pure helpers."""

from __future__ import annotations

from typing import Any

from vodoo.timer import (
    TIMESHEET_MODEL,
    TimerSource,
    Timesheet,
    _parse_stop_wizard,
    _resolve_timer_target,
    _StopWizardParams,
)


def _make_timesheet(
    *,
    source_kind: str = "task",
    source_id: int = 42,
    timesheet_id: int = 100,
) -> Timesheet:
    return Timesheet(
        id=timesheet_id,
        name="test",
        project_name=None,
        source=TimerSource(kind=source_kind, id=source_id, name="Test"),
        unit_amount=0,
        timer_start=None,
        date="2025-01-01",
    )


class TestResolveTimerTarget:
    def test_task(self) -> None:
        ts = _make_timesheet(source_kind="task", source_id=7)
        model, rec_id = _resolve_timer_target(ts)
        assert model == "project.task"
        assert rec_id == 7

    def test_ticket(self) -> None:
        ts = _make_timesheet(source_kind="ticket", source_id=3)
        model, rec_id = _resolve_timer_target(ts)
        assert model == "helpdesk.ticket"
        assert rec_id == 3

    def test_standalone(self) -> None:
        ts = _make_timesheet(source_kind="standalone", source_id=0, timesheet_id=99)
        model, rec_id = _resolve_timer_target(ts)
        assert model == TIMESHEET_MODEL
        assert rec_id == 99


class TestParseStopWizard:
    def test_returns_none_for_non_dict(self) -> None:
        assert _parse_stop_wizard(None) is None
        assert _parse_stop_wizard(True) is None
        assert _parse_stop_wizard("foo") is None

    def test_returns_none_for_non_wizard_dict(self) -> None:
        assert _parse_stop_wizard({"type": "other"}) is None
        assert _parse_stop_wizard({"type": "ir.actions.act_window"}) is None

    def test_legacy_wizard(self) -> None:
        result: dict[str, Any] = {
            "type": "ir.actions.act_window",
            "res_model": "project.task.create.timesheet",
            "context": {"active_id": 5, "default_time_spent": 1.5},
        }
        params = _parse_stop_wizard(result)
        assert isinstance(params, _StopWizardParams)
        assert params.res_model == "project.task.create.timesheet"
        assert params.values == {"task_id": 5, "description": "/", "time_spent": 1.5}
        assert params.method == "save_timesheet"

    def test_helpdesk_ticket_wizard(self) -> None:
        result: dict[str, Any] = {
            "type": "ir.actions.act_window",
            "res_model": "helpdesk.ticket.create.timesheet",
            "context": {"active_id": 8, "default_time_spent": 0.25},
        }
        params = _parse_stop_wizard(result)
        assert isinstance(params, _StopWizardParams)
        assert params.res_model == "helpdesk.ticket.create.timesheet"
        assert params.values == {"ticket_id": 8, "description": "/", "time_spent": 0.25}
        assert params.method == "action_generate_timesheet"

    def test_odoo19_wizard(self) -> None:
        result: dict[str, Any] = {
            "type": "ir.actions.act_window",
            "res_model": "hr.timesheet.stop.timer.confirmation.wizard",
            "context": {"default_timesheet_id": 10},
        }
        params = _parse_stop_wizard(result)
        assert isinstance(params, _StopWizardParams)
        assert params.res_model == "hr.timesheet.stop.timer.confirmation.wizard"
        assert params.values == {"timesheet_id": 10}
        assert params.method == "action_stop_timer"

    def test_unknown_wizard_model(self) -> None:
        result: dict[str, Any] = {
            "type": "ir.actions.act_window",
            "res_model": "some.unknown.wizard",
            "context": {},
        }
        assert _parse_stop_wizard(result) is None
