"""Central output-mode selection for the Vodoo CLI."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from typing import Any, Literal, Protocol, TextIO

from rich.console import Console

from vodoo.cli.rich import RichRenderer
from vodoo.cli.simple import SimpleRenderer
from vodoo.cli.structured import StructuredRenderer


class Renderer(Protocol):
    """Minimum contract shared by all CLI output renderers."""

    @property
    def mode(self) -> str:
        """Return the renderer's output mode."""

    @property
    def structured(self) -> bool:
        """Return whether the mode is machine-readable."""

    def write(self, value: Any) -> None:
        """Render one value."""


_renderer: Renderer = RichRenderer()


def configure_output(
    *,
    console: Console | None = None,
    simple: bool = False,
    json_mode: bool = False,
    toon_mode: bool = False,
    stream: TextIO | None = None,
) -> Renderer:
    """Select and install the renderer for the current CLI invocation."""
    global _renderer  # noqa: PLW0603
    selected = sum((simple, json_mode, toon_mode))
    if selected > 1:
        msg = "simple, JSON, and TOON output modes are mutually exclusive"
        raise ValueError(msg)
    if json_mode or toon_mode:
        output_format: Literal["json", "toon"] = "toon" if toon_mode else "json"
        _renderer = (
            StructuredRenderer(output_format, stream=stream)
            if stream is not None
            else StructuredRenderer(output_format)
        )
    elif simple:
        _renderer = SimpleRenderer(stream=stream) if stream is not None else SimpleRenderer()
    else:
        _renderer = RichRenderer(console or Console())
    return _renderer


def get_renderer() -> Renderer:
    """Return the active renderer."""
    return _renderer


def get_console() -> Console:
    """Return the active Rich console.

    Plain and structured modes do not use this method; returning a fallback
    keeps deprecated display-helper shims safe for direct callers.
    """
    if isinstance(_renderer, RichRenderer):
        return _renderer.console
    return Console()


def write(value: object = "") -> None:
    """Write one value through the active renderer."""
    _renderer.write(value)


def is_simple_output() -> bool:
    """Return whether plain TSV output is active."""
    return _renderer.mode == "simple"


def is_json_output() -> bool:
    """Return whether JSON output is active."""
    return _renderer.mode == "json"


def is_toon_output() -> bool:
    """Return whether TOON output is active."""
    return _renderer.mode == "toon"


def is_structured_output() -> bool:
    """Return whether a machine-readable output mode is active."""
    return _renderer.structured


def json_print(data: Any) -> None:
    """Write data as JSON regardless of the active mode."""
    StructuredRenderer("json").write(data)


def toon_print(data: Any) -> None:
    """Write data as TOON regardless of the active mode."""
    StructuredRenderer("toon").write(data)


def structured_print(data: Any) -> None:
    """Write data with the active structured renderer."""
    if not isinstance(_renderer, StructuredRenderer):
        StructuredRenderer("json").write(data)
        return
    _renderer.write(data)


def render_error(
    error: Exception,
    error_type: str,
    label: str,
    *,
    formatter: Callable[[Any], None] | None = None,
) -> None:
    """Render a CLI error without allowing formatter failures to mask it."""
    if not is_structured_output():
        get_console().print(f"[red]{label}:[/red] {error}")
        return

    payload = {"error": str(error), "type": error_type}
    try:
        (formatter or structured_print)(payload)
    except Exception:
        sys.stderr.write(f"{json.dumps(payload, ensure_ascii=False)}\n")
