"""Tests for the Claude Desktop extension bundle (packages/mcpb)."""

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("mcp")

from mcp.client.client import Client

from vodoo.mcp_server import create_server

BUNDLE = Path(__file__).resolve().parent.parent / "packages" / "mcpb"
MANIFEST = json.loads((BUNDLE / "manifest.json").read_text())


def _load_launcher() -> Any:
    spec = importlib.util.spec_from_file_location("vodoo_mcpb", BUNDLE / "src" / "vodoo_mcpb.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_manifest_lists_every_server_tool() -> None:
    server = create_server(client=object(), allow_write=True, allow_delete=True)  # type: ignore[arg-type]
    async with Client(server) as session:
        names = {tool.name for tool in (await session.list_tools()).tools}
    assert {tool["name"] for tool in MANIFEST["tools"]} == names


def test_manifest_env_uses_declared_settings() -> None:
    config = MANIFEST["server"]["mcp_config"]
    used = {
        value[len("${user_config.") : -1]
        for value in [*config["env"].values(), *config["args"]]
        if value.startswith("${user_config.")
    }
    assert used == set(MANIFEST["user_config"])
    assert MANIFEST["user_config"]["odoo_api_key"]["sensitive"] is True
    assert MANIFEST["user_config"]["allow_write"]["default"] is False
    assert MANIFEST["user_config"]["allow_delete"]["default"] is False


def test_launcher_treats_empty_and_placeholder_settings_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    launcher = _load_launcher()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("vodoo.mcp_server.run", lambda **kw: calls.append(kw))
    monkeypatch.setenv("ODOO_URL", "${user_config.odoo_url}")
    monkeypatch.setenv("ODOO_DATABASE", "")
    monkeypatch.setenv("ODOO_USERNAME", "me@example.com")
    monkeypatch.setenv("VODOO_MCP_INSTANCE", "${user_config.instance}")
    monkeypatch.setenv("VODOO_MCP_ALLOW_WRITE", "true")
    monkeypatch.setenv("VODOO_MCP_ALLOW_DELETE", "false")
    monkeypatch.setenv("VODOO_MCP_DOWNLOAD_DIR", "${user_config.download_dir}")
    monkeypatch.setattr(sys, "argv", ["vodoo_mcpb.py", "${user_config.upload_dirs}"])

    launcher.main()

    import os

    assert "ODOO_URL" not in os.environ
    assert "ODOO_DATABASE" not in os.environ
    assert os.environ["ODOO_USERNAME"] == "me@example.com"
    assert calls == [
        {
            "instance": None,
            "allow_write": True,
            "allow_delete": False,
            "download_dir": None,
            "upload_dirs": None,
        }
    ]


def test_launcher_passes_folders(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    launcher = _load_launcher()
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr("vodoo.mcp_server.run", lambda **kw: calls.append(kw))
    monkeypatch.setenv("VODOO_MCP_DOWNLOAD_DIR", str(tmp_path / "dl"))
    monkeypatch.setattr(sys, "argv", ["vodoo_mcpb.py", str(tmp_path / "a"), str(tmp_path / "b")])

    launcher.main()

    assert calls[0]["download_dir"] == tmp_path / "dl"
    assert calls[0]["upload_dirs"] == [tmp_path / "a", tmp_path / "b"]
    assert calls[0]["allow_write"] is False
