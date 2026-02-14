"""Async Odoo timer (timesheet) operations.

Mirrors :mod:`vodoo.timer` with async methods.
Reuses all data classes and parsing logic from the sync module.
"""

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

from vodoo.aio.client import AsyncOdooClient
from vodoo.timer import (
    BASE_FIELDS,
    TIMER_TIMER_DOMAIN,
    TIMER_TIMER_FIELDS,
    TIMESHEET_MODEL,
    TimerSource,
    Timesheet,
    _parse_odoo_datetime,
    _parse_timesheet,
    build_running_timer,
    merge_running_timers,
)

# -- Async timer backends --


class AsyncTimerBackend(ABC):
    """Version-specific async timer behavior."""

    @abstractmethod
    async def enrich_with_running_state(
        self,
        timesheets: list[Timesheet],
        client: AsyncOdooClient,
        uid: int,
    ) -> list[Timesheet]:
        """Enrich timesheets with running timer state."""

    @abstractmethod
    async def start_timer(self, timesheet: Timesheet, client: AsyncOdooClient) -> None:
        """Start a timer on a timesheet."""

    @abstractmethod
    async def stop_timer(self, timesheet: Timesheet, client: AsyncOdooClient) -> Any:
        """Stop a timer on a timesheet."""


class AsyncOdoo19TimerBackend(AsyncTimerBackend):
    """Async Odoo 19+: timers managed directly on account.analytic.line."""

    async def enrich_with_running_state(
        self,
        timesheets: list[Timesheet],
        client: AsyncOdooClient,  # noqa: ARG002
        uid: int,  # noqa: ARG002
    ) -> list[Timesheet]:
        return timesheets

    async def start_timer(self, timesheet: Timesheet, client: AsyncOdooClient) -> None:
        await client.execute(TIMESHEET_MODEL, "action_timer_start", [timesheet.id])

    async def stop_timer(self, timesheet: Timesheet, client: AsyncOdooClient) -> Any:
        return await client.execute(TIMESHEET_MODEL, "action_timer_stop", [timesheet.id])


class AsyncLegacyTimerBackend(AsyncTimerBackend):
    """Async Odoo 14-18: running timer state lives in timer.timer model."""

    async def enrich_with_running_state(
        self,
        timesheets: list[Timesheet],
        client: AsyncOdooClient,
        uid: int,
    ) -> list[Timesheet]:
        running_timers = await self._fetch_running_timers(client, uid)
        return merge_running_timers(timesheets, running_timers)

    async def start_timer(self, timesheet: Timesheet, client: AsyncOdooClient) -> None:
        if timesheet.source.kind == "task":
            await client.execute("project.task", "action_timer_start", [timesheet.source.id])
        elif timesheet.source.kind == "ticket":
            await client.execute("helpdesk.ticket", "action_timer_start", [timesheet.source.id])
        else:
            await client.execute(TIMESHEET_MODEL, "action_timer_start", [timesheet.id])

    async def stop_timer(self, timesheet: Timesheet, client: AsyncOdooClient) -> Any:
        if timesheet.source.kind == "task":
            return await client.execute("project.task", "action_timer_stop", [timesheet.source.id])
        if timesheet.source.kind == "ticket":
            return await client.execute(
                "helpdesk.ticket", "action_timer_stop", [timesheet.source.id]
            )
        return await client.execute(TIMESHEET_MODEL, "action_timer_stop", [timesheet.id])

    async def _fetch_running_timers(self, client: AsyncOdooClient, uid: int) -> list[Timesheet]:
        """Fetch running timers from timer.timer model."""
        try:
            records = await client.search_read(
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
                    task_records = await client.search_read(
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
                    ticket_records = await client.search_read(
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


# -- Async timer namespace --

# Cache keyed by client id to avoid repeated RPC probes within a session
_helpdesk_field_cache: dict[int, bool] = {}


class AsyncTimerNamespace:
    """Async namespace for timer (timesheet) operations."""

    def __init__(self, client: AsyncOdooClient) -> None:
        self._client = client

    async def today(self) -> list[Timesheet]:
        """Fetch today's timesheets for the current user."""
        uid = await self._client.get_uid()
        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        fields = await self._get_fields()

        records = await self._client.search_read(
            TIMESHEET_MODEL,
            domain=[["user_id", "=", uid], ["date", "=", today]],
            fields=fields,
        )

        timesheets = [ts for r in records if (ts := _parse_timesheet(r)) is not None]

        backend = self._get_backend()
        return await backend.enrich_with_running_state(timesheets, self._client, uid)

    async def active(self) -> list[Timesheet]:
        """Fetch currently running timesheets."""
        return [ts for ts in await self.today() if ts.timer_start is not None]

    async def start_task(self, task_id: int) -> None:
        """Start a timer on a project task."""
        await self._client.execute("project.task", "action_timer_start", [task_id])

    async def start_ticket(self, ticket_id: int) -> None:
        """Start a timer on a helpdesk ticket."""
        await self._client.execute("helpdesk.ticket", "action_timer_start", [ticket_id])

    async def start_timesheet(self, timesheet_id: int) -> None:
        """Start a timer on an existing timesheet."""
        fields = await self._get_fields()
        records = await self._client.search_read(
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
        await backend.start_timer(ts, self._client)

    async def stop_timesheet(self, timesheet_id: int) -> None:
        """Stop a timer on an existing timesheet."""
        fields = await self._get_fields()
        records = await self._client.search_read(
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
        result = await backend.stop_timer(ts, self._client)
        await self._handle_stop_wizard(result)

    async def stop(self) -> list[Timesheet]:
        """Stop all currently running timers."""
        active = await self.active()
        backend = self._get_backend()

        for ts in active:
            result = await backend.stop_timer(ts, self._client)
            await self._handle_stop_wizard(result)

        return active

    def _get_backend(self) -> AsyncTimerBackend:
        """Get the appropriate async timer backend based on the Odoo version."""
        if self._client.is_json2:
            return AsyncOdoo19TimerBackend()
        return AsyncLegacyTimerBackend()

    async def _has_helpdesk_field(self) -> bool:
        """Check if helpdesk_ticket_id field exists on timesheets (cached per client)."""
        key = id(self._client)
        if key in _helpdesk_field_cache:
            return _helpdesk_field_cache[key]
        try:
            await self._client.search_read(
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

    async def _get_fields(self) -> list[str]:
        """Get timesheet fields to fetch, including helpdesk if available."""
        fields = list(BASE_FIELDS)
        if await self._has_helpdesk_field():
            fields.append("helpdesk_ticket_id")
        return fields

    async def _handle_stop_wizard(self, result: Any) -> None:
        """Handle stop wizard if returned by action_timer_stop."""
        if not isinstance(result, dict):
            return

        res_model = result.get("res_model")
        if result.get("type") != "ir.actions.act_window" or not res_model:
            return

        context = result.get("context", {})

        if res_model == "project.task.create.timesheet":
            task_id = context.get("active_id", 0)
            time_spent = context.get("default_time_spent", 0)
            wizard_id = await self._client.create(
                res_model,
                {"task_id": task_id, "description": "/", "time_spent": time_spent},
            )
            await self._client.execute(res_model, "save_timesheet", [wizard_id], context=context)
        elif res_model == "hr.timesheet.stop.timer.confirmation.wizard":
            timesheet_id = context.get("default_timesheet_id", 0)
            wizard_id = await self._client.create(res_model, {"timesheet_id": timesheet_id})
            await self._client.execute(res_model, "action_stop_timer", [wizard_id], context=context)
