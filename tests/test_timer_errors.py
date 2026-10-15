"""Authoritative legacy timer access failures are not empty timer results."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from vodoo.aio.timer import AsyncLegacyTimerBackend, AsyncTimerNamespace
from vodoo.exceptions import OdooAccessError, TransportError
from vodoo.timer import LegacyTimerBackend, TimerNamespace


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("operation", ["list", "active", "stop"])
@pytest.mark.parametrize("failure", ["access", "transport", "empty"])
def test_legacy_timer_state_failures_propagate(
    asynchronous: bool, operation: str, failure: str
) -> None:
    client = MagicMock()
    client.is_json2 = False
    client.uid = 7
    error = (
        OdooAccessError("Timer read denied", code=403)
        if failure == "access"
        else TransportError("Offline")
    )
    responses = [[], [] if failure == "empty" else error]
    if asynchronous:
        client.get_uid = AsyncMock(return_value=7)
        client.search_read = AsyncMock(side_effect=responses)
        namespace = AsyncTimerNamespace(client)
        namespace._helpdesk_field = False

        def invoke() -> Any:
            return asyncio.run(getattr(namespace, operation)())

    else:
        client.search_read.side_effect = responses
        namespace = TimerNamespace(client)
        namespace._helpdesk_field = False

        def invoke() -> Any:
            return getattr(namespace, operation)()

    if failure == "empty":
        assert invoke() == []
    else:
        with pytest.raises(type(error)) as caught:
            invoke()
        assert caught.value is error
    assert client.search_read.call_args.args[0] == "timer.timer"
    client.execute.assert_not_called()


@pytest.mark.parametrize("asynchronous", [False, True])
@pytest.mark.parametrize("source_model", ["project.task", "helpdesk.ticket"])
def test_optional_legacy_timer_label_access_stays_best_effort(
    asynchronous: bool, source_model: str
) -> None:
    client = MagicMock()
    records = [
        {"id": 50, "timer_start": "2025-01-02 10:00:00", "res_model": source_model, "res_id": 4}
    ]
    error = OdooAccessError("Source label read denied", code=403)
    if asynchronous:
        client.search_read = AsyncMock(side_effect=[records, error])
        result = asyncio.run(AsyncLegacyTimerBackend().enrich_with_running_state([], client, 7))
    else:
        client.search_read.side_effect = [records, error]
        result = LegacyTimerBackend().enrich_with_running_state([], client, 7)
    assert len(result) == 1
    assert result[0].timer_start is not None
    assert result[0].source.id == 4
    assert result[0].source.name == ("Task #4" if source_model == "project.task" else "Ticket #4")
