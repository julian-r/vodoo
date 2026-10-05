"""Best-effort preflight checks: importantly, these tests do not assert CAS."""

import asyncio
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import httpx2 as httpx
import pytest
from typer.testing import CliRunner

import vodoo.main as main_module
from vodoo import (
    AsyncOdooClient,
    Markdown,
    OdooClient,
    OdooConfig,
    RevisionInputError,
    StaleRevisionError,
    UnverifiableRevisionError,
)
from vodoo.aio.transport import AsyncJSON2Transport, AsyncLegacyTransport
from vodoo.cli.output import configure_output
from vodoo.exceptions import OdooAccessError, RecordNotFoundError, TransportError
from vodoo.transport import JSON2Transport, LegacyTransport, RetryConfig

EXPECTED = "2026-10-03 13:00:20"
CURRENT = "2026-10-03 13:00:21"
MODEL = "project.task"


def make_client(async_mode: bool = False) -> tuple[Any, MagicMock]:
    transport = MagicMock()
    transport.read.return_value = [{"id": 42, "write_date": EXPECTED}]
    transport.write.return_value = True
    transport.execute_kw.return_value = {"name": {"type": "char"}}
    if async_mode:
        transport.read = AsyncMock(return_value=transport.read.return_value)
        transport.write = AsyncMock(return_value=True)
    config = OdooConfig(
        url="https://mock.odoo.test", database="testdb", username="admin", password="secret"
    )
    cls = AsyncOdooClient if async_mode else OdooClient
    return cls(config, transport=transport), transport


def mutate(
    client: Any,
    async_mode: bool,
    endpoint: str = "write",
    expected: str | None = EXPECTED,
    values: dict[str, Any] | None = None,
) -> bool:
    values = values if values is not None else {"name": "mine"}
    kwargs = {} if expected is None else {"check_write_date": expected}
    if endpoint == "set":
        result = client.tasks.set(42, values, **kwargs)
    elif endpoint == "update":
        result = client.generic.update(MODEL, 42, values, **kwargs)
    else:
        result = client.write(MODEL, [42], values, **kwargs)
    return asyncio.run(result) if async_mode else result


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("endpoint", ["write", "set", "update"])
def test_matching_preflight_then_immediate_prepared_write(async_mode: bool, endpoint: str) -> None:
    client, transport = make_client(async_mode)
    assert mutate(client, async_mode, endpoint, values={"name": Markdown("**mine**")})
    assert transport.mock_calls == [
        call.read(MODEL, [42], ["write_date"]),
        call.write(MODEL, [42], {"name": "<p><strong>mine</strong></p>"}),
    ]


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("endpoint", ["write", "set", "update"])
def test_default_remains_unguarded(async_mode: bool, endpoint: str) -> None:
    client, transport = make_client(async_mode)
    assert mutate(client, async_mode, endpoint, expected=None)
    transport.read.assert_not_called()
    transport.write.assert_called_once_with(MODEL, [42], {"name": "mine"})


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize("endpoint", ["write", "set", "update"])
def test_stale_observation_does_not_write(async_mode: bool, endpoint: str) -> None:
    client, transport = make_client(async_mode)
    transport.read.return_value = [{"id": 42, "write_date": CURRENT}]
    with pytest.raises(StaleRevisionError) as caught:
        mutate(client, async_mode, endpoint)
    assert caught.value.expected == EXPECTED
    assert caught.value.current == CURRENT
    assert caught.value.code == "stale_preflight_conflict"
    transport.write.assert_not_called()


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize(
    "revision",
    [
        "",
        "2026-02-30 13:00:20",
        "2026-1-3 13:00:20",
        "2026-10-03T13:00:20Z",
        EXPECTED + ".123456",
        EXPECTED + " ",
        "2026-10-03 25:00:20",
    ],
)
def test_malformed_expected_does_not_read_or_write(async_mode: bool, revision: str) -> None:
    client, transport = make_client(async_mode)
    with pytest.raises(RevisionInputError):
        mutate(client, async_mode, expected=revision)
    transport.read.assert_not_called()
    transport.write.assert_not_called()


@pytest.mark.parametrize("async_mode", [False, True])
def test_missing_record_does_not_write(async_mode: bool) -> None:
    client, transport = make_client(async_mode)
    transport.read.return_value = []
    with pytest.raises(RecordNotFoundError):
        mutate(client, async_mode)
    transport.write.assert_not_called()


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize(
    "observation",
    [
        {"id": 42},
        {"id": 42, "write_date": False},
        {"id": 42, "write_date": None},
        {"id": 42, "write_date": "invalid"},
        {"id": 42, "write_date": 123},
    ],
)
def test_unusable_observation_fails_closed(async_mode: bool, observation: dict[str, Any]) -> None:
    client, transport = make_client(async_mode)
    transport.read.return_value = [observation]
    with pytest.raises(UnverifiableRevisionError):
        mutate(client, async_mode)
    transport.write.assert_not_called()


@pytest.mark.parametrize("async_mode", [False, True])
def test_access_error_is_not_conflict_or_deletion(async_mode: bool) -> None:
    client, transport = make_client(async_mode)
    error = OdooAccessError("Not allowed")
    transport.read.side_effect = error
    with pytest.raises(OdooAccessError) as caught:
        mutate(client, async_mode)
    assert caught.value is error
    transport.write.assert_not_called()


@pytest.mark.parametrize("async_mode", [False, True])
def test_ambiguous_mutation_failure_is_not_retried_or_conflict(async_mode: bool) -> None:
    client, transport = make_client(async_mode)
    error = TransportError("Connection lost; outcome unknown")
    transport.write.side_effect = error
    with pytest.raises(TransportError) as caught:
        mutate(client, async_mode)
    assert caught.value is error
    assert transport.write.call_count == 1
    assert transport.read.call_count == 1


@pytest.mark.parametrize("async_mode", [False, True])
def test_controlled_intervening_write_demonstrates_remaining_race(async_mode: bool) -> None:
    client, transport = make_client(async_mode)
    state = {"name": "old", "write_date": EXPECTED}

    def write_after_another_writer(model: str, ids: list[int], values: dict[str, Any]) -> bool:
        assert model == MODEL
        assert ids == [42]
        # A writer commits after the preflight read and before our ordinary write.
        state.update(name="concurrent change", write_date=CURRENT)
        state.update(values)
        return True

    transport.write.side_effect = write_after_another_writer
    assert mutate(client, async_mode)
    assert state == {"name": "mine", "write_date": CURRENT}  # Newer value overwritten!
    assert transport.read.call_count == 1


@pytest.mark.parametrize("async_mode", [False, True])
def test_seconds_precision_cannot_detect_same_second_change(async_mode: bool) -> None:
    first = datetime(2026, 10, 3, 13, 0, 20, 100000, tzinfo=UTC)
    second = first.replace(microsecond=900000)
    assert first != second
    assert first.strftime("%Y-%m-%d %H:%M:%S") == second.strftime("%Y-%m-%d %H:%M:%S")
    client, transport = make_client(async_mode)
    transport.read.return_value = [{"id": 42, "write_date": second.strftime("%Y-%m-%d %H:%M:%S")}]
    assert mutate(client, async_mode, expected=first.strftime("%Y-%m-%d %H:%M:%S"))
    transport.write.assert_called_once()


def test_bulk_write_checks_every_id_before_writing() -> None:
    client, transport = make_client()
    transport.read.return_value = [
        {"id": 42, "write_date": EXPECTED},
        {"id": 43, "write_date": CURRENT},
    ]
    with pytest.raises(StaleRevisionError):
        client.write(MODEL, [42, 43], {"name": "mine"}, check_write_date=EXPECTED)
    transport.write.assert_not_called()


@pytest.fixture(autouse=True)
def reset_output() -> Iterator[None]:
    configure_output()
    yield
    configure_output()


COMMANDS = [
    ("project-task", "set"),
    ("project", "set"),
    ("helpdesk", "set"),
    ("crm", "set"),
    ("model", "update", MODEL),
]


@pytest.mark.parametrize("command", COMMANDS)
def test_cli_forwards_matching_check_after_field_preparation(
    monkeypatch: pytest.MonkeyPatch, command: tuple[str, ...]
) -> None:
    client, transport = make_client()
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    result = CliRunner().invoke(
        main_module.app, ["--json", *command, "42", "name=mine", "--check-write-date", EXPECTED]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["ok"] is True
    names = [entry[0] for entry in transport.mock_calls]
    assert names[-2:] == ["read", "write"]


@pytest.mark.parametrize("structured", [False, True])
def test_cli_stale_error_expected_current_and_distinct_exit(
    monkeypatch: pytest.MonkeyPatch, structured: bool
) -> None:
    client, transport = make_client()
    transport.read.return_value = [{"id": 42, "write_date": CURRENT}]
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    result = CliRunner().invoke(
        main_module.app,
        [
            *(["--json"] if structured else []),
            "project-task",
            "set",
            "42",
            "name=mine",
            "--check-write-date",
            EXPECTED,
        ],
    )
    assert result.exit_code == 3, result.output
    assert EXPECTED in result.output
    assert CURRENT in result.output
    if structured:
        payload = json.loads(result.output)
        assert payload["code"] == payload["type"] == "stale_preflight_conflict"
        assert payload["expected"] == EXPECTED
        assert payload["current"] == CURRENT
        assert payload["mutation_attempted"] is False
        assert payload["best_effort"] is True
    transport.write.assert_not_called()


@pytest.mark.parametrize(
    ("revision", "records", "exit_code", "error_type"),
    [
        ("malformed", [{"id": 42, "write_date": EXPECTED}], 2, "invalid_revision"),
        (EXPECTED, [], 1, "not_found"),
        (EXPECTED, [{"id": 42, "write_date": False}], 1, "unverifiable_revision"),
    ],
)
def test_cli_non_conflict_revision_errors(
    monkeypatch: pytest.MonkeyPatch,
    revision: str,
    records: list[dict[str, Any]],
    exit_code: int,
    error_type: str,
) -> None:
    client, transport = make_client()
    transport.read.return_value = records
    monkeypatch.setattr(main_module, "get_client", lambda: client)
    result = CliRunner().invoke(
        main_module.app,
        ["--json", "model", "update", MODEL, "42", "name=mine", "--check-write-date", revision],
    )
    assert result.exit_code == exit_code
    assert json.loads(result.output)["type"] == error_type
    transport.write.assert_not_called()


@pytest.mark.parametrize("command", COMMANDS)
def test_cli_help_advertises_non_atomic_limitations(command: tuple[str, ...]) -> None:
    result = CliRunner().invoke(main_module.app, [*command[:2], "--help"])
    assert result.exit_code == 0
    assert "--check-write-date" in result.output
    assert "non-atomic" in result.output


@pytest.mark.parametrize(
    "cls", [LegacyTransport, JSON2Transport, AsyncLegacyTransport, AsyncJSON2Transport]
)
def test_transport_never_retries_write_after_timeout(cls: type[Any]) -> None:
    transport = object.__new__(cls)
    transport.retry = RetryConfig(max_retries=5)
    assert not transport._is_retryable("write", httpx.ReadTimeout("ambiguous outcome"))
    assert not transport._is_retryable("write", httpx.ConnectError("connection failed"))
    assert transport._is_retryable("read", httpx.ReadTimeout("retryable read"))


@pytest.mark.parametrize(
    "cls", [LegacyTransport, JSON2Transport, AsyncLegacyTransport, AsyncJSON2Transport]
)
def test_actual_transport_write_timeout_is_sent_once(cls: type[Any]) -> None:
    transport = object.__new__(cls)
    transport.retry = RetryConfig(max_retries=5)
    transport._uid = 1
    transport.database = "testdb"
    transport.password = "secret"
    async_mode = cls in (AsyncLegacyTransport, AsyncJSON2Transport)
    failure = httpx.ReadTimeout("Mutation may already have committed")
    request = AsyncMock(side_effect=failure) if async_mode else MagicMock(side_effect=failure)
    if cls in (LegacyTransport, AsyncLegacyTransport):
        transport.call_service = request
    else:
        transport._request = request

    def send_write() -> None:
        result = transport.write(MODEL, [42], {"name": "mine"})
        if async_mode:
            asyncio.run(result)

    with pytest.raises(httpx.ReadTimeout):
        send_write()
    assert request.call_count == 1
