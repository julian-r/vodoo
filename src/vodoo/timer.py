"""Odoo timer (timesheet) operations.

Supports starting/stopping timers on tasks, tickets, and timesheets.
Handles version-specific differences:
- Odoo 19+: timers live directly on account.analytic.line
- Odoo 14-18: timers live in timer.timer; start/stop via source model
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from vodoo.client import OdooClient

TIMESHEET_MODEL = "account.analytic.line"

BASE_FIELDS = [
    "name",
    "project_id",
    "task_id",
    "unit_amount",
    "timer_start",
    "date",
]


class TimerState(StrEnum):
    """Timer state."""

    RUNNING = "running"
    STOPPED = "stopped"


@dataclass
class TimerSource:
    """Source of a timer (task, ticket, or standalone timesheet)."""

    kind: str  # "task", "ticket", or "standalone"
    id: int  # source record ID (0 for standalone)
    name: str  # display name

    @property
    def icon(self) -> str:
        icons = {"task": "🔧", "ticket": "🎫", "standalone": "⏱"}
        return icons.get(self.kind, "⏱")

    @property
    def model(self) -> str:
        models = {"task": "project.task", "ticket": "helpdesk.ticket"}
        return models.get(self.kind, TIMESHEET_MODEL)


@dataclass
class Timesheet:
    """A timesheet entry from Odoo's account.analytic.line model."""

    id: int
    name: str
    project_name: str | None
    source: TimerSource
    unit_amount: float
    timer_start: datetime | None
    date: str

    @property
    def state(self) -> TimerState:
        return TimerState.RUNNING if self.timer_start else TimerState.STOPPED

    @property
    def elapsed(self) -> timedelta:
        """Calculate elapsed time including live running time."""
        base = timedelta(hours=self.unit_amount)
        if self.timer_start:
            base += datetime.now(tz=UTC) - self.timer_start
        return base

    @property
    def elapsed_formatted(self) -> str:
        """Format elapsed time as H:MM."""
        total_seconds = int(self.elapsed.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}:{minutes:02d}"

    @property
    def display_label(self) -> str:
        label = self.source.name if self.source.kind != "standalone" else (self.name or "Timesheet")
        return f"{self.source.icon} {label}"


# -- Timer backends --


class TimerBackend(ABC):
    """Version-specific timer behavior."""

    @abstractmethod
    def enrich_with_running_state(
        self,
        timesheets: list[Timesheet],
        client: OdooClient,
        uid: int,
    ) -> list[Timesheet]:
        """Enrich timesheets with running timer state."""

    @abstractmethod
    def start_timer(self, timesheet: Timesheet, client: OdooClient) -> None:
        """Start a timer on a timesheet."""

    @abstractmethod
    def stop_timer(self, timesheet: Timesheet, client: OdooClient) -> Any:
        """Stop a timer on a timesheet. Returns wizard action dict if any."""


class Odoo19TimerBackend(TimerBackend):
    """Odoo 19+: timers managed directly on account.analytic.line."""

    def enrich_with_running_state(
        self,
        timesheets: list[Timesheet],
        client: OdooClient,  # noqa: ARG002
        uid: int,  # noqa: ARG002
    ) -> list[Timesheet]:
        # timer_start on the timesheet is already authoritative
        return timesheets

    def start_timer(self, timesheet: Timesheet, client: OdooClient) -> None:
        client.execute(TIMESHEET_MODEL, "action_timer_start", [timesheet.id])

    def stop_timer(self, timesheet: Timesheet, client: OdooClient) -> Any:
        return client.execute(TIMESHEET_MODEL, "action_timer_stop", [timesheet.id])


class LegacyTimerBackend(TimerBackend):
    """Odoo 14-18: running timer state lives in timer.timer model."""

    def enrich_with_running_state(
        self,
        timesheets: list[Timesheet],
        client: OdooClient,
        uid: int,
    ) -> list[Timesheet]:
        running_timers = self._fetch_running_timers(client, uid)
        return merge_running_timers(timesheets, running_timers)

    def start_timer(self, timesheet: Timesheet, client: OdooClient) -> None:
        if timesheet.source.kind == "task":
            client.execute("project.task", "action_timer_start", [timesheet.source.id])
        elif timesheet.source.kind == "ticket":
            client.execute("helpdesk.ticket", "action_timer_start", [timesheet.source.id])
        else:
            client.execute(TIMESHEET_MODEL, "action_timer_start", [timesheet.id])

    def stop_timer(self, timesheet: Timesheet, client: OdooClient) -> Any:
        if timesheet.source.kind == "task":
            return client.execute("project.task", "action_timer_stop", [timesheet.source.id])
        if timesheet.source.kind == "ticket":
            return client.execute("helpdesk.ticket", "action_timer_stop", [timesheet.source.id])
        return client.execute(TIMESHEET_MODEL, "action_timer_stop", [timesheet.id])

    def _fetch_running_timers(self, client: OdooClient, uid: int) -> list[Timesheet]:
        """Fetch running timers from timer.timer model."""
        try:
            records = client.search_read(
                "timer.timer",
                domain=[["user_id", "=", uid], *TIMER_TIMER_DOMAIN],
                fields=TIMER_TIMER_FIELDS,
            )
        except Exception:
            return []

        timesheets: list[Timesheet] = []
        for record in records:
            res_model = record.get("res_model")
            res_id = record.get("res_id")
            timer_start_str = record.get("timer_start")
            if not res_model or not res_id or not timer_start_str:
                continue

            timer_start = _parse_odoo_datetime(timer_start_str)
            if timer_start is None:
                continue

            source: TimerSource
            project_name: str | None = None

            if res_model == "project.task":
                try:
                    task_records = client.search_read(
                        "project.task",
                        domain=[["id", "=", res_id]],
                        fields=["display_name", "project_id"],
                        limit=1,
                    )
                    name = (
                        task_records[0].get("display_name", f"Task #{res_id}")
                        if task_records
                        else f"Task #{res_id}"
                    )
                    proj = task_records[0].get("project_id") if task_records else None
                    if isinstance(proj, list) and len(proj) >= 2:
                        project_name = str(proj[1])
                except Exception:
                    name = f"Task #{res_id}"
                source = TimerSource(kind="task", id=res_id, name=name)
            elif res_model == "helpdesk.ticket":
                try:
                    ticket_records = client.search_read(
                        "helpdesk.ticket",
                        domain=[["id", "=", res_id]],
                        fields=["display_name"],
                        limit=1,
                    )
                    name = (
                        ticket_records[0].get("display_name", f"Ticket #{res_id}")
                        if ticket_records
                        else f"Ticket #{res_id}"
                    )
                except Exception:
                    name = f"Ticket #{res_id}"
                source = TimerSource(kind="ticket", id=res_id, name=name)
            else:
                continue

            timesheets.append(build_running_timer(record, source, project_name, timer_start))

        return timesheets


# -- Pure helpers --


TIMER_TIMER_DOMAIN = [
    ["timer_start", "!=", False],
    ["timer_pause", "=", False],
]
TIMER_TIMER_FIELDS = ["timer_start", "res_model", "res_id"]


def merge_running_timers(
    timesheets: list[Timesheet],
    running_timers: list[Timesheet],
) -> list[Timesheet]:
    """Merge running timer info into existing timesheets.

    Shared by both sync and async legacy backends.
    """
    result = list(timesheets)

    for timer in running_timers:
        source_id = timer.source.id
        match_idx: int | None = None

        for i, ts in enumerate(result):
            if ts.source.kind == timer.source.kind and ts.source.id == source_id:
                match_idx = i
                break

        if match_idx is not None:
            existing = result[match_idx]
            result[match_idx] = Timesheet(
                id=existing.id,
                name=existing.name,
                project_name=existing.project_name,
                source=existing.source,
                unit_amount=existing.unit_amount,
                timer_start=timer.timer_start,
                date=existing.date,
            )
        else:
            result.append(timer)

    return result


def build_running_timer(
    record: dict[str, Any],
    source: TimerSource,
    project_name: str | None,
    timer_start: datetime,
) -> Timesheet:
    """Build a Timesheet representing a running timer from timer.timer data."""
    timer_id = -(record.get("id", source.id))
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    return Timesheet(
        id=timer_id,
        name="",
        project_name=project_name,
        source=source,
        unit_amount=0,
        timer_start=timer_start,
        date=today,
    )


def _parse_many2one(value: Any) -> tuple[int, str] | None:
    """Parse a many2one field value [id, name]."""
    if isinstance(value, list) and len(value) >= 2:
        rec_id = value[0]
        name = value[1]
        if isinstance(rec_id, int) and isinstance(name, str):
            return (rec_id, name)
    return None


def _parse_odoo_datetime(value: Any) -> datetime | None:
    """Parse Odoo datetime string to UTC datetime."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_source(record: dict[str, Any]) -> TimerSource:
    """Determine the source (task, ticket, or standalone) of a timesheet."""
    task = _parse_many2one(record.get("task_id"))
    if task:
        return TimerSource(kind="task", id=task[0], name=task[1])
    ticket = _parse_many2one(record.get("helpdesk_ticket_id"))
    if ticket:
        return TimerSource(kind="ticket", id=ticket[0], name=ticket[1])
    return TimerSource(kind="standalone", id=0, name="")


def _parse_timesheet(record: dict[str, Any]) -> Timesheet | None:
    """Parse an Odoo record into a Timesheet."""
    rec_id = record.get("id")
    if not isinstance(rec_id, int):
        return None

    project = _parse_many2one(record.get("project_id"))
    return Timesheet(
        id=rec_id,
        name=record.get("name", ""),
        project_name=project[1] if project else None,
        source=_parse_source(record),
        unit_amount=record.get("unit_amount", 0) or 0,
        timer_start=_parse_odoo_datetime(record.get("timer_start")),
        date=record.get("date", ""),
    )


# -- Timer namespace --

# Cache keyed by client id to avoid repeated RPC probes within a session
_helpdesk_field_cache: dict[int, bool] = {}


class TimerNamespace:
    """Namespace for timer (timesheet) operations."""

    def __init__(self, client: OdooClient) -> None:
        self._client = client

    def today(self) -> list[Timesheet]:
        """Fetch today's timesheets for the current user."""
        uid = self._client.uid
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        fields = self._get_fields()

        records = self._client.search_read(
            TIMESHEET_MODEL,
            domain=[["user_id", "=", uid], ["date", "=", today]],
            fields=fields,
        )

        timesheets = [ts for r in records if (ts := _parse_timesheet(r)) is not None]

        backend = self._get_backend()
        return backend.enrich_with_running_state(timesheets, self._client, uid)

    def active(self) -> list[Timesheet]:
        """Fetch currently running timesheets."""
        return [ts for ts in self.today() if ts.timer_start is not None]

    def start_task(self, task_id: int) -> None:
        """Start a timer on a project task."""
        self._client.execute("project.task", "action_timer_start", [task_id])

    def start_ticket(self, ticket_id: int) -> None:
        """Start a timer on a helpdesk ticket."""
        self._client.execute("helpdesk.ticket", "action_timer_start", [ticket_id])

    def start_timesheet(self, timesheet_id: int) -> None:
        """Start a timer on an existing timesheet."""
        fields = self._get_fields()
        records = self._client.search_read(
            TIMESHEET_MODEL,
            domain=[["id", "=", timesheet_id]],
            fields=fields,
            limit=1,
        )
        if not records:
            msg = f"Timesheet {timesheet_id} not found"
            raise ValueError(msg)

        ts = _parse_timesheet(records[0])
        if ts is None:
            msg = f"Failed to parse timesheet {timesheet_id}"
            raise ValueError(msg)

        backend = self._get_backend()
        backend.start_timer(ts, self._client)

    def stop_timesheet(self, timesheet_id: int) -> None:
        """Stop a timer on an existing timesheet.

        Handles stop wizards automatically (Odoo 14-18 and 19).
        """
        fields = self._get_fields()
        records = self._client.search_read(
            TIMESHEET_MODEL,
            domain=[["id", "=", timesheet_id]],
            fields=fields,
            limit=1,
        )
        if not records:
            msg = f"Timesheet {timesheet_id} not found"
            raise ValueError(msg)

        ts = _parse_timesheet(records[0])
        if ts is None:
            msg = f"Failed to parse timesheet {timesheet_id}"
            raise ValueError(msg)

        backend = self._get_backend()
        result = backend.stop_timer(ts, self._client)
        self._handle_stop_wizard(result)

    def stop(self) -> list[Timesheet]:
        """Stop all currently running timers."""
        active = self.active()
        backend = self._get_backend()

        for ts in active:
            result = backend.stop_timer(ts, self._client)
            self._handle_stop_wizard(result)

        return active

    def _get_backend(self) -> TimerBackend:
        """Get the appropriate timer backend based on the Odoo version."""
        if self._client.is_json2:
            return Odoo19TimerBackend()
        return LegacyTimerBackend()

    def _has_helpdesk_field(self) -> bool:
        """Check if helpdesk_ticket_id field exists on timesheets (cached per client)."""
        key = id(self._client)
        if key in _helpdesk_field_cache:
            return _helpdesk_field_cache[key]
        try:
            self._client.search_read(
                TIMESHEET_MODEL,
                domain=[],
                fields=["id", "helpdesk_ticket_id"],
                limit=1,
            )
            result = True
        except Exception:
            result = False
        _helpdesk_field_cache[key] = result
        return result

    def _get_fields(self) -> list[str]:
        """Get timesheet fields to fetch, including helpdesk if available."""
        fields = list(BASE_FIELDS)
        if self._has_helpdesk_field():
            fields.append("helpdesk_ticket_id")
        return fields

    def _handle_stop_wizard(self, result: Any) -> None:
        """Handle stop wizard if returned by action_timer_stop.

        Some Odoo versions return a wizard action instead of stopping directly.
        """
        if not isinstance(result, dict):
            return

        res_model = result.get("res_model")
        if result.get("type") != "ir.actions.act_window" or not res_model:
            return

        context = result.get("context", {})

        if res_model == "project.task.create.timesheet":
            # Odoo 14-18 stop wizard
            task_id = context.get("active_id", 0)
            time_spent = context.get("default_time_spent", 0)
            wizard_id = self._client.create(
                res_model,
                {"task_id": task_id, "description": "/", "time_spent": time_spent},
            )
            self._client.execute(res_model, "save_timesheet", [wizard_id], context=context)
        elif res_model == "hr.timesheet.stop.timer.confirmation.wizard":
            # Odoo 19 stop wizard
            timesheet_id = context.get("default_timesheet_id", 0)
            wizard_id = self._client.create(res_model, {"timesheet_id": timesheet_id})
            self._client.execute(res_model, "action_stop_timer", [wizard_id], context=context)
