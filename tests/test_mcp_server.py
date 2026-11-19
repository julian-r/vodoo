"""Unit tests for the Vodoo MCP server (no Odoo needed: uses a fake client)."""

import base64
import json
import logging
from pathlib import Path
from typing import Any, ClassVar

import pytest

pytest.importorskip("mcp")

from mcp.client.client import Client

from vodoo.exceptions import OdooAccessError
from vodoo.mcp_server import create_server
from vodoo.mcp_server.server import MoveLine, _contains_delete_command

pytestmark = pytest.mark.anyio

READ_TOOLS = {
    "odoo_info",
    "search_records",
    "count_records",
    "read_records",
    "get_fields",
    "name_search",
    "get_record_url",
    "list_messages",
    "list_attachments",
    "download_attachment",
    "list_account_moves",
    "get_account_move",
    "list_timesheets",
    "timer_status",
}
WRITE_TOOLS = {
    "create_record",
    "update_records",
    "call_method",
    "post_message",
    "attach_file",
    "create_account_move",
    "post_account_moves",
    "reset_account_moves_to_draft",
    "cancel_account_moves",
    "register_payment",
    "mark_activity_done",
    "timer_start",
    "timer_stop",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


SECRET = "sk-test-0123456789abcdef"


class _Config:
    url = "https://odoo.example.com"
    database = "prod"
    default_user_id = None
    password = SECRET + "\n"
    http_headers: ClassVar[dict[str, str]] = {"X-Proxy": "Bearer proxytoken-987654321"}


class FakeClient:
    """Records calls; returns canned data."""

    def __init__(self) -> None:
        self.config = _Config()
        self.is_json2 = True
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.search_read_result: list[dict[str, Any]] = []
        self.read_result: dict[str, list[dict[str, Any]]] = {}
        self.execute_result: dict[str, Any] = {}
        self.next_id = 100
        self.fail_with: Exception | None = None

    def _log(self, name: str, *args: Any, **kwargs: Any) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append((name, args, kwargs))

    def called(self, name: str) -> list[tuple[tuple[Any, ...], dict[str, Any]]]:
        return [(a, k) for n, a, k in self.calls if n == name]

    async def get_uid(self) -> int:
        return 2

    async def search_read(self, model: str, **kwargs: Any) -> list[dict[str, Any]]:
        self._log("search_read", model, **kwargs)
        return [dict(r) for r in self.search_read_result]

    async def read(self, model: str, ids: list[int], fields: Any = None) -> list[dict[str, Any]]:
        self._log("read", model, ids, fields)
        return [dict(r) for r in self.read_result.get(model, [{"id": i} for i in ids])]

    async def search(self, model: str, domain: Any = None, **_kwargs: Any) -> list[int]:
        self._log("search", model, domain)
        return [7]

    async def execute(self, model: str, method: str, *args: Any, **kwargs: Any) -> Any:
        self._log("execute", model, method, *args, **kwargs)
        return self.execute_result.get(method, True)

    async def create(self, model: str, values: dict[str, Any], context: Any = None) -> int:
        self._log("create", model, values, context=context)
        self.next_id += 1
        return self.next_id

    async def write(self, model: str, ids: list[int], values: dict[str, Any], **kw: Any) -> bool:
        self._log("write", model, ids, values, **kw)
        return True

    async def unlink(self, model: str, ids: list[int]) -> bool:
        self._log("unlink", model, ids)
        return True

    async def fields_get(self, model: str, **kwargs: Any) -> dict[str, Any]:
        self._log("fields_get", model, **kwargs)
        return {"name": {"type": "char"}, "image_1920": {"type": "binary"}}

    async def name_search(self, model: str, name: str, **kwargs: Any) -> list[tuple[int, str]]:
        self._log("name_search", model, name, **kwargs)
        return [(5, "Acme Corp")]

    async def close(self) -> None:  # pragma: no cover - not owned by server
        raise AssertionError("server must not close an injected client")


async def _call(
    client: FakeClient, tool: str, args: dict[str, Any] | None = None, **server_kw: Any
) -> tuple[bool, Any]:
    server = create_server(client=client, **server_kw)  # type: ignore[arg-type]
    async with Client(server) as session:
        result = await session.call_tool(tool, args or {})
    text = result.content[0].text if result.content else ""
    if result.is_error:
        return True, text
    return False, json.loads(text)


async def _tool_names(**server_kw: Any) -> set[str]:
    server = create_server(client=FakeClient(), **server_kw)  # type: ignore[arg-type]
    async with Client(server) as session:
        return {t.name for t in (await session.list_tools()).tools}


# ── Tool registration / modes ─────────────────────────────────────────────


async def test_read_only_by_default() -> None:
    assert await _tool_names() == READ_TOOLS


async def test_allow_write_adds_write_tools_but_not_delete() -> None:
    assert await _tool_names(allow_write=True) == READ_TOOLS | WRITE_TOOLS


async def test_allow_delete_adds_delete_tool() -> None:
    names = await _tool_names(allow_write=True, allow_delete=True)
    assert names == READ_TOOLS | WRITE_TOOLS | {"delete_records"}


async def test_annotations_mark_read_and_destructive_tools() -> None:
    server = create_server(client=FakeClient(), allow_write=True)  # type: ignore[arg-type]
    async with Client(server) as session:
        tools = {t.name: t for t in (await session.list_tools()).tools}
    assert tools["search_records"].annotations.read_only_hint is True
    assert tools["post_account_moves"].annotations.read_only_hint is False
    assert tools["post_account_moves"].annotations.destructive_hint is True
    assert tools["create_record"].annotations.destructive_hint is False
    assert tools["create_account_move"].annotations.destructive_hint is True


async def test_write_tool_is_unknown_in_read_only_mode() -> None:
    is_error, text = await _call(FakeClient(), "create_record", {"model": "x", "values": {}})
    assert is_error
    assert "create_record" in text


# ── Read tools ────────────────────────────────────────────────────────────


async def test_search_records_known_model_uses_curated_fields() -> None:
    client = FakeClient()
    client.search_read_result = [{"id": 1, "name": "INV/1"}]
    is_error, data = await _call(client, "search_records", {"model": "account.move"})
    assert not is_error
    (_, kwargs) = client.called("search_read")[0]
    assert "amount_total" in kwargs["fields"]
    assert data["total"] == 1
    assert data["records"] == [{"id": 1, "name": "INV/1"}]


async def test_search_records_unknown_model_defaults_to_display_name() -> None:
    client = FakeClient()
    await _call(client, "search_records", {"model": "res.partner"})
    (_, kwargs) = client.called("search_read")[0]
    assert kwargs["fields"] == ["id", "display_name"]


async def test_search_records_counts_when_page_is_full() -> None:
    client = FakeClient()
    client.search_read_result = [{"id": 1}, {"id": 2}]
    client.execute_result["search_count"] = 42
    _, data = await _call(client, "search_records", {"model": "res.partner", "limit": 2})
    assert data["total"] == 42
    (args, _) = client.called("execute")[0]
    assert args[:2] == ("res.partner", "search_count")


@pytest.mark.parametrize(
    ("returned", "offset", "expected_count_call"),
    [(1, 0, False), (0, 0, False), (0, 100, True), (2, 0, True), (1, 10, False)],
)
async def test_search_records_total(returned: int, offset: int, expected_count_call: bool) -> None:
    client = FakeClient()
    client.search_read_result = [{"id": i} for i in range(returned)]
    client.execute_result["search_count"] = 7
    _, data = await _call(
        client, "search_records", {"model": "res.partner", "limit": 2, "offset": offset}
    )
    assert bool(client.called("execute")) is expected_count_call
    assert data["total"] == (7 if expected_count_call else returned + offset)


async def test_search_records_rejects_negative_offset() -> None:
    is_error, _ = await _call(FakeClient(), "search_records", {"model": "x", "offset": -1})
    assert is_error


async def test_search_records_clamps_limit() -> None:
    client = FakeClient()
    await _call(client, "search_records", {"model": "res.partner", "limit": 100000})
    (_, kwargs) = client.called("search_read")[0]
    assert kwargs["limit"] == 500


async def test_read_records_unknown_model_skips_binary_fields() -> None:
    client = FakeClient()
    await _call(client, "read_records", {"model": "res.partner", "ids": [5]})
    (args, _) = client.called("read")[0]
    assert args[2] == ["name"]


async def test_messages_are_converted_to_markdown() -> None:
    client = FakeClient()
    client.search_read_result = [{"id": 1, "body": "<p>Hello <strong>world</strong></p>"}]
    _, data = await _call(client, "list_messages", {"model": "account.move", "record_id": 1})
    assert data[0]["body"] == "Hello **world**"


async def test_list_account_moves_builds_domain() -> None:
    client = FakeClient()
    await _call(
        client,
        "list_account_moves",
        {
            "move_type": "out_invoice",
            "state": "posted",
            "payment_state": "not_paid",
            "date_from": "2026-01-01",
        },
    )
    (_, kwargs) = client.called("search_read")[0]
    domain = kwargs["domain"]
    assert ("move_type", "=", "out_invoice") in domain
    assert ("state", "=", "posted") in domain
    assert ("payment_state", "=", "not_paid") in domain
    assert ("date", ">=", "2026-01-01") in domain


async def test_empty_list_result_is_one_json_block() -> None:
    is_error, data = await _call(FakeClient(), "list_attachments", {"model": "x", "record_id": 1})
    assert not is_error
    assert data == []


async def test_odoo_errors_are_reported_to_the_model() -> None:
    client = FakeClient()
    client.fail_with = OdooAccessError("Access denied on account.move")
    is_error, text = await _call(client, "search_records", {"model": "account.move"})
    assert is_error
    assert "Access denied on account.move" in text


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError(f"header value {SECRET!r}\\n is invalid"),
        OdooAccessError(f"bad key {SECRET}"),
        OdooAccessError("proxy said Bearer proxytoken-987654321"),
    ],
)
async def test_errors_never_contain_credentials(
    error: Exception, caplog: pytest.LogCaptureFixture
) -> None:
    client = FakeClient()
    client.fail_with = error
    with caplog.at_level(logging.DEBUG):
        is_error, text = await _call(client, "search_records", {"model": "account.move"})
    assert is_error
    for leaked in (SECRET, "proxytoken-987654321"):
        assert leaked not in text
        assert leaked not in caplog.text


async def test_short_credentials_are_redacted(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeClient()
    client.config = _Config()
    client.config.password = "abc"
    client.config.http_headers = {"X-Key": "q9"}
    client.fail_with = OdooAccessError("denied for key abc and header q9")
    with caplog.at_level(logging.DEBUG):
        is_error, text = await _call(client, "search_records", {"model": "account.move"})
    assert is_error
    assert "[redacted]" in text
    for leaked in ("abc", "q9"):
        assert leaked not in text
        assert leaked not in caplog.text


async def test_unexpected_errors_are_generic() -> None:
    client = FakeClient()
    client.fail_with = RuntimeError("internal detail")
    _, text = await _call(client, "search_records", {"model": "account.move"})
    assert text.endswith("Unexpected error (RuntimeError). See the MCP server log.")
    assert "internal detail" not in text


async def test_download_attachment_sanitizes_name_and_never_overwrites(tmp_path: Path) -> None:
    client = FakeClient()
    client.read_result["ir.attachment"] = [
        {
            "id": 9,
            "name": "../../evil.pdf",
            "mimetype": "application/pdf",
            "datas": base64.b64encode(b"%PDF").decode(),
        }
    ]
    (tmp_path / "evil.pdf").write_bytes(b"existing")
    _, data = await _call(
        client, "download_attachment", {"attachment_id": 9}, download_dir=tmp_path
    )
    path = Path(data["path"])
    assert path.parent == tmp_path.resolve()
    assert path.name == "evil (1).pdf"
    assert path.read_bytes() == b"%PDF"
    assert (tmp_path / "evil.pdf").read_bytes() == b"existing"


def _attachment_client() -> FakeClient:
    client = FakeClient()
    client.read_result["ir.attachment"] = [
        {"id": 9, "name": "a.pdf", "datas": base64.b64encode(b"%PDF").decode()}
    ]
    return client


@pytest.mark.parametrize("output_dir", ["/tmp", "../outside", "sub/../../outside", ".hidden"])
async def test_download_refuses_folders_outside_the_download_dir(
    tmp_path: Path, output_dir: str
) -> None:
    root = tmp_path / "downloads"
    is_error, text = await _call(
        _attachment_client(),
        "download_attachment",
        {"attachment_id": 9, "output_dir": output_dir},
        download_dir=root,
    )
    assert is_error
    assert "must be inside" in text
    assert not (tmp_path / "outside").exists()


async def test_download_into_subfolder(tmp_path: Path) -> None:
    _, data = await _call(
        _attachment_client(),
        "download_attachment",
        {"attachment_id": 9, "output_dir": "2026/bills"},
        download_dir=tmp_path,
    )
    assert Path(data["path"]) == (tmp_path / "2026" / "bills" / "a.pdf").resolve()


async def test_download_refuses_symlink_escape(tmp_path: Path) -> None:
    root, outside = tmp_path / "downloads", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "link").symlink_to(outside)
    is_error, _ = await _call(
        _attachment_client(),
        "download_attachment",
        {"attachment_id": 9, "output_dir": "link"},
        download_dir=root,
    )
    assert is_error
    assert not list(outside.iterdir())


async def test_download_does_not_follow_existing_symlink_file(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_bytes(b"keep")
    root = tmp_path / "downloads"
    root.mkdir()
    (root / "a.pdf").symlink_to(target)
    _, data = await _call(
        _attachment_client(), "download_attachment", {"attachment_id": 9}, download_dir=root
    )
    assert Path(data["path"]).name == "a (1).pdf"
    assert target.read_bytes() == b"keep"


async def test_attach_file_only_from_allowed_folders(tmp_path: Path) -> None:
    allowed, other = tmp_path / "allowed", tmp_path / "other"
    for folder in (allowed, other, allowed / ".secret"):
        folder.mkdir()
    (allowed / "bill.pdf").write_bytes(b"%PDF")
    (allowed / ".env").write_bytes(b"PASSWORD=x")
    (allowed / ".secret" / "key.pem").write_bytes(b"key")
    (other / "id_rsa").write_bytes(b"key")
    (allowed / "escape.pdf").symlink_to(other / "id_rsa")
    server_kw = {"allow_write": True, "upload_dirs": [allowed], "download_dir": tmp_path / "dl"}

    for refused in (
        other / "id_rsa",
        allowed / ".env",
        allowed / ".secret" / "key.pem",
        allowed / "escape.pdf",
        allowed / "missing.pdf",
        allowed,
    ):
        client = FakeClient()
        is_error, text = await _call(
            client,
            "attach_file",
            {"model": "account.move", "record_id": 1, "file_path": str(refused)},
            **server_kw,
        )
        assert is_error, refused
        assert "Can only attach" in text
        assert not client.called("create")

    client = FakeClient()
    is_error, data = await _call(
        client,
        "attach_file",
        {"model": "account.move", "record_id": 1, "file_path": str(allowed / "bill.pdf")},
        **server_kw,
    )
    assert not is_error, data
    assert data["name"] == "bill.pdf"


# ── Write tools ───────────────────────────────────────────────────────────


async def test_create_invoice_uses_invoice_lines_and_tax_commands() -> None:
    client = FakeClient()
    client.read_result["account.move"] = [{"id": 101, "move_type": "out_invoice"}]
    is_error, _ = await _call(
        client,
        "create_account_move",
        {
            "move_type": "out_invoice",
            "partner_id": 5,
            "invoice_date": "2026-11-19",
            "lines": [{"name": "Consulting", "quantity": 2, "price_unit": 150, "tax_ids": [3]}],
        },
        allow_write=True,
    )
    assert not is_error
    (args, kwargs) = client.called("create")[0]
    model, values = args
    assert model == "account.move"
    assert values["partner_id"] == 5
    line = {"name": "Consulting", "quantity": 2.0, "price_unit": 150.0, "tax_ids": [(6, 0, [3])]}
    assert values["invoice_line_ids"] == [(0, 0, line)]
    assert kwargs["context"] == {"default_move_type": "out_invoice"}
    assert not client.called("execute")  # not posted


async def test_create_entry_uses_line_ids_and_can_post() -> None:
    client = FakeClient()
    client.read_result["account.move"] = [{"id": 101, "move_type": "entry", "line_ids": [1, 2]}]
    await _call(
        client,
        "create_account_move",
        {
            "move_type": "entry",
            "post": True,
            "lines": [
                {"account_id": 10, "debit": 100},
                {"account_id": 11, "credit": 100},
            ],
        },
        allow_write=True,
    )
    (args, _) = client.called("create")[0]
    assert "line_ids" in args[1]
    assert "invoice_line_ids" not in args[1]
    (exec_args, _) = client.called("execute")[0]
    assert exec_args[:2] == ("account.move", "action_post")


async def test_create_invoice_requires_partner() -> None:
    is_error, text = await _call(
        FakeClient(),
        "create_account_move",
        {"move_type": "in_invoice", "lines": [{"name": "x", "price_unit": 1}]},
        allow_write=True,
    )
    assert is_error
    assert "partner_id" in text


async def test_register_payment_runs_wizard_with_active_ids() -> None:
    client = FakeClient()
    client.execute_result["action_create_payments"] = {"res_model": "account.payment", "res_id": 55}
    client.read_result["account.move"] = [
        {"id": 10, "name": "INV/10", "state": "posted", "amount_residual": 50.0}
    ]
    _, data = await _call(
        client,
        "register_payment",
        {"move_ids": [10], "amount": 50.0, "memo": "INV/10"},
        allow_write=True,
    )
    (args, kwargs) = client.called("create")[0]
    assert args[0] == "account.payment.register"
    assert args[1] == {"amount": 50.0, "communication": "INV/10"}
    assert kwargs["context"] == {"active_model": "account.move", "active_ids": [10]}
    (exec_args, exec_kwargs) = client.called("execute")[0]
    assert exec_args[1] == "action_create_payments"
    assert exec_kwargs["context"]["active_ids"] == [10]
    assert data["payments"] == [{"id": 55}]


async def test_register_payment_refuses_unpostable_moves() -> None:
    client = FakeClient()
    client.read_result["account.move"] = [
        {"id": 10, "name": "INV/10", "state": "cancel", "amount_residual": 50.0},
        {"id": 11, "name": "INV/11", "state": "posted", "payment_state": "paid"},
    ]
    is_error, text = await _call(
        client, "register_payment", {"move_ids": [10, 11, 12]}, allow_write=True
    )
    assert is_error
    assert "10 (INV/10): state is cancel" in text
    assert "11 (INV/11): nothing left to pay" in text
    assert "12: not found" in text
    assert not client.called("create")


@pytest.mark.parametrize("method", ["unlink", "action_unlink", "Unlink"])
async def test_call_method_cannot_delete_without_flag(method: str) -> None:
    client = FakeClient()
    is_error, text = await _call(
        client,
        "call_method",
        {"model": "res.partner", "method": method, "ids": [1]},
        allow_write=True,
    )
    assert is_error
    assert "--allow-delete" in text
    assert not client.called("execute")


async def test_call_method_can_delete_with_flag() -> None:
    client = FakeClient()
    is_error, _ = await _call(
        client,
        "call_method",
        {"model": "res.partner", "method": "unlink", "ids": [1]},
        allow_write=True,
        allow_delete=True,
    )
    assert not is_error
    assert client.called("execute")


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        (
            "update_records",
            {"model": "account.move", "ids": [1], "values": {"line_ids": [[2, 5, 0]]}},
        ),
        ("create_record", {"model": "res.partner", "values": {"child_ids": [[2, 5]]}}),
        (
            "call_method",
            {
                "model": "account.move",
                "method": "write",
                "ids": [1],
                "kwargs": {"vals": {"invoice_line_ids": [[2, 5, 0]]}},
            },
        ),
        (
            "create_account_move",
            {
                "move_type": "entry",
                "lines": [{"account_id": 1, "debit": 1}],
                "extra_values": {"line_ids": [[2, 9, 0]]},
            },
        ),
    ],
)
async def test_x2many_delete_command_needs_flag(tool: str, args: dict[str, Any]) -> None:
    client = FakeClient()
    is_error, text = await _call(client, tool, args, allow_write=True)
    assert is_error
    assert "--allow-delete" in text
    assert not client.called("write")
    assert not client.called("create")
    assert not client.called("execute")


async def test_x2many_delete_command_allowed_with_flag() -> None:
    client = FakeClient()
    is_error, _ = await _call(
        client,
        "update_records",
        {"model": "account.move", "ids": [1], "values": {"line_ids": [[2, 5, 0]]}},
        allow_write=True,
        allow_delete=True,
    )
    assert not is_error


@pytest.mark.parametrize(
    "command",
    [[2, 5, 0], [2, 5], [2.0, 5, 0], [2, 5.0, 0], [2, 5, 0, "extra"], (2, 5, 0)],
)
def test_contains_delete_command_catches_all_forms(command: Any) -> None:
    assert _contains_delete_command({"line_ids": [command]})
    assert _contains_delete_command({"line_ids": [[1, 3, {"sub_ids": [command]}]]})
    assert _contains_delete_command({"line_ids": [[1.0, 3, {"sub_ids": [command]}, 9]]})


async def test_noncanonical_delete_command_needs_flag() -> None:
    client = FakeClient()
    is_error, _ = await _call(
        client,
        "update_records",
        {"model": "account.move", "ids": [1], "values": {"line_ids": [[2.0, 5, 0]]}},
        allow_write=True,
    )
    assert is_error
    assert not client.called("write")


def test_contains_delete_command_ignores_ordinary_values() -> None:
    assert not _contains_delete_command({"tag_ids": [[6, 0, [2, 5]]], "x": [2, 5]})
    assert not _contains_delete_command({"line_ids": [[1, 2, {"name": "x"}], [3, 2, 0]]})
    assert not _contains_delete_command({"domain": [["id", "=", 2]]})
    assert _contains_delete_command({"a": {"b": [[0, 0, {"c": [[2, 1, 0]]}]]}})


async def test_call_method_rejects_private_methods() -> None:
    is_error, text = await _call(
        FakeClient(),
        "call_method",
        {"model": "account.move", "method": "_compute_amount", "ids": [1]},
        allow_write=True,
    )
    assert is_error
    assert "Private" in text


async def test_call_method_passes_ids_and_kwargs() -> None:
    client = FakeClient()
    await _call(
        client,
        "call_method",
        {"model": "sale.order", "method": "action_confirm", "ids": [3], "kwargs": {"x": 1}},
        allow_write=True,
    )
    (args, kwargs) = client.called("execute")[0]
    assert args == ("sale.order", "action_confirm", [3])
    assert kwargs == {"x": 1}


async def test_post_message_defaults_to_internal_note() -> None:
    client = FakeClient()
    client.execute_result["check_object_reference"] = ["mail.message.subtype", 1]
    client.read_result["res.users"] = [{"partner_id": [3, "Me"]}]
    is_error, data = await _call(
        client,
        "post_message",
        {"model": "account.move", "record_id": 1, "message": "**Checked**"},
        allow_write=True,
    )
    assert not is_error, data
    assert data["internal"] is True
    values = next(a[1] for a, _ in client.called("create") if a[0] == "mail.message")
    assert values["message_type"] == "notification"
    assert "<strong>Checked</strong>" in values["body"]


async def test_delete_records() -> None:
    client = FakeClient()
    _, data = await _call(
        client,
        "delete_records",
        {"model": "account.move", "ids": [1, 2]},
        allow_write=True,
        allow_delete=True,
    )
    assert data == {"deleted": [1, 2], "ok": True}


def test_move_line_to_values_merges_extra() -> None:
    line = MoveLine(name="A", price_unit=1.0, tax_ids=[], extra={"analytic_distribution": {}})
    assert line.to_values() == {
        "name": "A",
        "price_unit": 1.0,
        "tax_ids": [(6, 0, [])],
        "analytic_distribution": {},
    }


def test_quiet_http_logs_hides_header_debug_lines() -> None:
    from vodoo.mcp_server.server import _quiet_http_logs

    _quiet_http_logs()
    for name in ("httpx", "httpx2", "httpcore", "httpcore2"):
        assert not logging.getLogger(name).isEnabledFor(logging.INFO)
