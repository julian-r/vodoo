"""Shared transport conformance plus neutral Python date/binary adapters."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx2 as httpx
import pytest

from vodoo.aio.transport import AsyncJSON2Transport
from vodoo.client import _normalize_false
from vodoo.cmd import Cmd
from vodoo.exceptions import TransportError, transport_error_from_data
from vodoo.helpdesk import HelpdeskNamespace
from vodoo.transport import (
    _RETRYABLE_METHODS,
    JSON2Transport,
    LegacyTransport,
    RetryConfig,
    _build_json2_body,
    _coerce_created_id,
    _parse_json2_response,
    _parse_name_search,
)

FIXTURE_PATH = Path(__file__).parents[2] / "conformance" / "fixtures" / "v1.json"
FIXTURE: dict[str, Any] = json.loads(FIXTURE_PATH.read_text())


def _ids(rows: list[dict[str, Any]]) -> list[str]:
    return [str(row["id"]) for row in rows]


@pytest.mark.parametrize("scenario", FIXTURE["json2Bodies"], ids=_ids(FIXTURE["json2Bodies"]))
def test_json2_body_contract(scenario: dict[str, Any]) -> None:
    if scenario.get("expectError") == "TypeError":
        with pytest.raises(TypeError):
            _build_json2_body(scenario["method"], scenario["args"], scenario.get("kwargs"))
        return
    assert (
        _build_json2_body(scenario["method"], scenario["args"], scenario.get("kwargs"))
        == scenario["expect"]
    )


@pytest.mark.parametrize("scenario", FIXTURE["json2Responses"], ids=_ids(FIXTURE["json2Responses"]))
def test_json2_response_contract(scenario: dict[str, Any]) -> None:
    assert _parse_json2_response(scenario["wire"].encode()) == scenario["expect"]


def test_name_search_contract() -> None:
    scenario = FIXTURE["nameSearch"]
    assert [list(item) for item in _parse_name_search(scenario["input"])] == scenario["expect"]


@pytest.mark.parametrize("scenario", FIXTURE["errors"], ids=_ids(FIXTURE["errors"]))
def test_error_mapping_contract(scenario: dict[str, Any]) -> None:
    error = transport_error_from_data(scenario["message"], scenario["code"], scenario["data"])
    assert type(error).__name__ == scenario["class"]
    assert str(error) == scenario["rendered"]
    assert error.code == scenario["code"]
    assert error.data == scenario["data"]


def _parse_contract_date(scenario: dict[str, Any]) -> datetime:
    try:
        if scenario["kind"] == "date":
            value = date.fromisoformat(scenario["wire"])
            return datetime(value.year, value.month, value.day, tzinfo=UTC)
        return datetime.strptime(scenario["wire"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    except ValueError as error:
        raise TypeError(f"Invalid Odoo {scenario['kind']}: {scenario['wire']}") from error


@pytest.mark.parametrize("scenario", FIXTURE["dates"], ids=_ids(FIXTURE["dates"]))
def test_date_contract(scenario: dict[str, Any]) -> None:
    if scenario.get("expectError") == "TypeError":
        with pytest.raises(TypeError):
            _parse_contract_date(scenario)
        return
    parsed = _parse_contract_date(scenario)
    assert parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z") == scenario["iso"]
    wire = parsed.strftime("%Y-%m-%d" if scenario["kind"] == "date" else "%Y-%m-%d %H:%M:%S")
    assert wire == scenario["wire"]


@pytest.mark.parametrize("scenario", FIXTURE["binary"], ids=_ids(FIXTURE["binary"]))
def test_binary_contract(scenario: dict[str, Any]) -> None:
    value = bytes(scenario["bytes"])
    encoded = base64.b64encode(value).decode("ascii")
    assert encoded == scenario["base64"]
    assert list(base64.b64decode(encoded, validate=True)) == scenario["bytes"]


@pytest.mark.parametrize("scenario", FIXTURE["commands"], ids=_ids(FIXTURE["commands"]))
def test_command_contract(scenario: dict[str, Any]) -> None:
    operation = getattr(Cmd, scenario["operation"])
    assert list(operation(*scenario["args"])) == scenario["expect"]


@pytest.mark.parametrize("scenario", FIXTURE["retry"], ids=_ids(FIXTURE["retry"]))
def test_retry_contract(scenario: dict[str, Any]) -> None:
    assert (scenario["method"] in _RETRYABLE_METHODS) is scenario["retryable"]
    retry = RetryConfig(max_retries=2, backoff_base=0.5, backoff_max=30.0)
    assert retry.delay(scenario["attempt"]) * 1000 == scenario["delayMs"]


@pytest.mark.parametrize("scenario", FIXTURE["normalization"], ids=_ids(FIXTURE["normalization"]))
def test_normalization_contract(scenario: dict[str, Any]) -> None:
    assert _normalize_false([dict(scenario["input"])]) == [scenario["expect"]]


class _RecordingCreateClient:
    def __init__(self, result: int) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        self.calls.append((model, values, context))
        return self.result


@pytest.mark.parametrize("scenario", FIXTURE["operations"], ids=_ids(FIXTURE["operations"]))
def test_operation_contract(scenario: dict[str, Any]) -> None:
    client = _RecordingCreateClient(scenario["expectedResult"])
    namespace = HelpdeskNamespace(client)  # type: ignore[arg-type]
    values = scenario["input"]
    result = namespace.create(
        values["name"],
        description=values["description"],
        partner_id=values["partnerId"],
        tag_ids=values["tagIds"],
        team_id=values["teamId"],
        **values["extraFields"],
    )
    assert result == scenario["expectedResult"]
    expected_values = dict(scenario["expectedValues"])
    expected_values["tag_ids"] = [Cmd.set(values["tagIds"])]
    assert client.calls == [(scenario["expectedModel"], expected_values, None)]


@pytest.mark.parametrize("scenario", FIXTURE["createResults"], ids=_ids(FIXTURE["createResults"]))
def test_create_result_contract(scenario: dict[str, Any]) -> None:
    if scenario.get("expectError"):
        with pytest.raises(TransportError):
            _coerce_created_id(scenario["wire"])
    else:
        assert _coerce_created_id(scenario["wire"]) == scenario["expect"]


def _canonical_request(request: httpx.Request, expected: dict[str, Any]) -> dict[str, Any]:
    return {
        "method": request.method,
        "path": request.url.path,
        "headers": {name: request.headers[name] for name in expected["headers"]},
        "json": json.loads(request.content),
    }


@pytest.mark.parametrize("scenario", FIXTURE["transports"], ids=_ids(FIXTURE["transports"]))
def test_transport_wire_contract(scenario: dict[str, Any]) -> None:
    responses = list(scenario["responses"])
    expected_requests = scenario["expect"]["requests"]
    requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        expected = expected_requests[len(requests)]
        requests.append(_canonical_request(request, expected))
        response = responses.pop(0)
        return httpx.Response(response["status"], json=response["body"])

    config = scenario["config"]
    transport_type = JSON2Transport if scenario["dialect"] == "json2" else LegacyTransport
    transport = transport_type(
        config["url"],
        config["database"],
        config["username"],
        config["password"],
        retry=RetryConfig(max_retries=0),
    )
    transport._http.close()
    transport._http = httpx.Client(transport=httpx.MockTransport(handler))
    invoke = scenario["invoke"]
    try:
        if invoke["operation"] == "searchRead":
            value = transport.search_read(
                invoke["model"],
                domain=invoke["domain"],
                fields=invoke["fields"],
                limit=invoke["limit"],
                offset=invoke["offset"],
                order=invoke["order"],
            )
        else:
            value = transport.search(
                invoke["model"],
                domain=invoke["domain"],
                limit=invoke["limit"],
                offset=invoke["offset"],
                order=invoke["order"],
            )
    finally:
        transport.close()

    assert value == scenario["expect"]["value"]
    assert requests == expected_requests
    assert responses == []


def test_opaque_password_contract() -> None:
    transport = JSON2Transport("https://odoo.example.test", " db ", " user ", " key ")
    async_transport = AsyncJSON2Transport("https://odoo.example.test", " db ", " user ", " key ")
    try:
        for candidate in (transport, async_transport):
            assert candidate.database == "db"
            assert candidate.username == "user"
            assert candidate.password == " key "
    finally:
        transport.close()
        asyncio.run(async_transport.close())
