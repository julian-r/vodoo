"""Renderer boundary for composite task context."""

import json
from typing import Any

from rich.text import Text

from vodoo.cli.output import get_renderer, is_structured_output, structured_print


def display_task_context(context: dict[str, Any]) -> None:
    """Render the full payload, including errors and continuation, in every mode.

    Plain output is one TSV line per top-level key, with a JSON-encoded value.
    Escaping embedded newlines/tabs keeps arbitrary task/chatter text pipe-safe.
    """
    if is_structured_output():
        structured_print(context)
        return
    renderer = get_renderer()
    for key, value in context.items():
        line = f"{key}\t{json.dumps(value, ensure_ascii=False, sort_keys=True)}"
        renderer.write(Text(line) if renderer.mode == "rich" else line)
