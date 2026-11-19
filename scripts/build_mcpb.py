#!/usr/bin/env python3
"""Build the Claude Desktop extension (``.mcpb``) for the Vodoo MCP server.

The bundle uses the MCPB ``uv`` runtime: Claude Desktop installs Python and the
dependencies itself. The bundle carries the vodoo wheel built from this checkout,
so its version always matches the source.

Usage:
    uv run python scripts/build_mcpb.py            # -> dist/vodoo-<version>.mcpb

Requires ``uv`` and ``npx`` (for the ``@anthropic-ai/mcpb`` packer).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "packages" / "mcpb"
MCPB_CLI = "@anthropic-ai/mcpb@2"

PYPROJECT = """\
[project]
name = "vodoo-mcpb"
version = "{version}"
description = "Claude Desktop extension launcher for the Vodoo MCP server"
requires-python = ">=3.12"
dependencies = ["vodoo[mcp]"]

[tool.uv]
package = false

[tool.uv.sources]
vodoo = {{ path = "wheels/{wheel}" }}
"""


def _run(*cmd: str, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd, check=True)


def _semver(version: str) -> str:
    """PEP 440 (4.3.2.dev1+g41f1d2c) -> SemVer (4.3.2-dev.1+g41f1d2c)."""
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:\.?(dev|a|b|rc)(\d+))?(?:\+(.+))?", version)
    if not match:
        return version
    core, pre, number, local = match.groups()
    result = core + (f"-{pre}.{number}" if pre else "")
    return result + (f"+{local}" if local else "")


def tool_list() -> list[dict[str, str]]:
    """Every server tool (all modes) with the first line of its description."""
    import asyncio

    from mcp.client.client import Client

    from vodoo.mcp_server import create_server

    async def collect() -> list[dict[str, str]]:
        server = create_server(
            client=object(),  # type: ignore[arg-type]
            allow_write=True,
            allow_delete=True,
            hide_unavailable=False,
        )
        async with Client(server) as session:
            tools = (await session.list_tools()).tools
        return [
            {"name": t.name, "description": (t.description or "").splitlines()[0]} for t in tools
        ]

    return asyncio.run(collect())


def build(output_dir: Path) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _run("uv", "build", "--wheel", "--out-dir", str(tmp_path / "wheel"), cwd=ROOT)
        wheel = next((tmp_path / "wheel").glob("vodoo-*.whl"))
        version = wheel.name.split("-")[1]

        stage = tmp_path / "vodoo"
        shutil.copytree(SOURCE, stage, ignore=shutil.ignore_patterns("__pycache__", ".venv"))
        (stage / "wheels").mkdir()
        shutil.copy(wheel, stage / "wheels" / wheel.name)
        (stage / "pyproject.toml").write_text(PYPROJECT.format(version=version, wheel=wheel.name))

        manifest_path = stage / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["version"] = _semver(version)
        manifest["tools"] = tool_list()
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

        _run("uv", "lock", "--directory", str(stage))
        _run("npx", "-y", MCPB_CLI, "validate", str(manifest_path))

        output_dir.mkdir(parents=True, exist_ok=True)
        bundle = output_dir / f"vodoo-{version}.mcpb"
        _run("npx", "-y", MCPB_CLI, "pack", str(stage), str(bundle))
        return bundle


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    bundle = build(args.out_dir)
    print(f"Built {bundle}")


if __name__ == "__main__":
    main()
