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
    TIMESHEET_MODEL,
    TimerSource,
    Timesheet,
    _parse_odoo_datetime,
    _parse_timesheet,
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
                domain=[
                    ["user_id", "=", uid],
                    ["timer_start", "!=", False],
                    ["timer_pause", "=", False],
                ],
                fields=["timer_start", "res_model", "res_id"],
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

            timer_id = -(record.get("id", res_id))
            today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
            timesheets.append(
                Timesheet(
                    id=timer_id,
                    name="",
                    project_name=project_name,
                    source=source,
                    unit_amount=0,
                    timer_start=timer_start,
                    date=today,
                )
            )

        return timesheets


# -- Async timer service --


def get_timer_backend(client: AsyncOdooClient) -> AsyncTimerBackend:
    """Get the appropriate async timer backend based on the Odoo version."""
    from vodoo.aio.transport import AsyncJSON2Transport

    if isinstance(client._transport, AsyncJSON2Transport):
        return AsyncOdoo19TimerBackend()
    return AsyncLegacyTimerBackend()


async def _has_helpdesk_field(client: AsyncOdooClient) -> bool:
    """Check if helpdesk_ticket_id field exists on timesheets."""
    try:
        await client.search_read(
            TIMESHEET_MODEL,
            domain=[],
            fields=["id", "helpdesk_ticket_id"],
            limit=1,
        )
    except Exception:
        return False
    return True


async def _get_fields(client: AsyncOdooClient) -> list[str]:
    """Get timesheet fields to fetch, including helpdesk if available."""
    fields = list(BASE_FIELDS)
    if await _has_helpdesk_field(client):
        fields.append("helpdesk_ticket_id")
    return fields


async def fetch_today_timesheets(client: AsyncOdooClient) -> list[Timesheet]:
    """Fetch today's timesheets for the current user."""
    uid = await client.get_uid()
    today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    fields = await _get_fields(client)

    records = await client.search_read(
        TIMESHEET_MODEL,
        domain=[["user_id", "=", uid], ["date", "=", today]],
        fields=fields,
    )

    timesheets = [ts for r in records if (ts := _parse_timesheet(r)) is not None]

    backend = get_timer_backend(client)
    return await backend.enrich_with_running_state(timesheets, client, uid)


async def fetch_active_timesheets(client: AsyncOdooClient) -> list[Timesheet]:
    """Fetch currently running timesheets."""
    return [ts for ts in await fetch_today_timesheets(client) if ts.timer_start is not None]


async def start_timer_on_task(client: AsyncOdooClient, task_id: int) -> None:
    """Start a timer on a project task."""
    await client.execute("project.task", "action_timer_start", [task_id])


async def start_timer_on_ticket(client: AsyncOdooClient, ticket_id: int) -> None:
    """Start a timer on a helpdesk ticket."""
    await client.execute("helpdesk.ticket", "action_timer_start", [ticket_id])


async def start_timer_on_timesheet(client: AsyncOdooClient, timesheet_id: int) -> None:
    """Start a timer on an existing timesheet."""
    fields = await _get_fields(client)
    records = await client.search_read(
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

    backend = get_timer_backend(client)
    await backend.start_timer(ts, client)


async def stop_timer_on_timesheet(client: AsyncOdooClient, timesheet_id: int) -> None:
    """Stop a timer on an existing timesheet."""
    fields = await _get_fields(client)
    records = await client.search_read(
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

    backend = get_timer_backend(client)
    result = await backend.stop_timer(ts, client)
    await _handle_stop_wizard(client, result)


async def stop_active_timers(client: AsyncOdooClient) -> list[Timesheet]:
    """Stop all currently running timers."""
    active = await fetch_active_timesheets(client)
    backend = get_timer_backend(client)

    for ts in active:
        result = await backend.stop_timer(ts, client)
        await _handle_stop_wizard(client, result)

    return active


async def _handle_stop_wizard(client: AsyncOdooClient, result: Any) -> None:
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
        wizard_id = await client.create(
            res_model,
            {"task_id": task_id, "description": "/", "time_spent": time_spent},
        )
        await client.execute(res_model, "save_timesheet", [wizard_id], context=context)
    elif res_model == "hr.timesheet.stop.timer.confirmation.wizard":
        timesheet_id = context.get("default_timesheet_id", 0)
        wizard_id = await client.create(res_model, {"timesheet_id": timesheet_id})
        await client.execute(res_model, "action_stop_timer", [wizard_id], context=context)
