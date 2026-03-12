"""Content type wrappers for Odoo HTML fields.

Vodoo assumes text is **markdown by default**.  Use :class:`HTML` when you
need to pass pre-built HTML through without conversion.

Examples::

    from vodoo.content import Markdown, HTML

    # Explicit markdown (same as bare str in domain helpers)
    create_task(client, "My task", project_id=1,
                description=Markdown("# Heading\\n\\n- item 1"))

    # Bypass conversion — pass raw HTML
    create_task(client, "My task", project_id=1,
                description=HTML("<h1>Heading</h1>"))
"""

from __future__ import annotations

from typing import Any


class Markdown(str):
    """Marker: value is markdown and should be converted to HTML before sending."""


class HTML(str):
    """Marker: value is already HTML and should be sent as-is."""


def _markdown_to_html(text: str) -> str:
    """Convert markdown text to HTML."""
    import markdown as md

    return md.markdown(
        text,
        extensions=["extra", "nl2br", "sane_lists"],
    )


def process_values(values: dict[str, Any]) -> dict[str, Any]:
    """Walk a values dict and convert content-typed entries.

    - :class:`Markdown` → converted to HTML via the ``markdown`` library.
    - :class:`HTML` → unwrapped to a plain ``str`` (no conversion).
    - Plain ``str`` → left unchanged (backward compatible).

    Non-string values are passed through untouched.
    """
    out: dict[str, Any] = {}
    for key, val in values.items():
        if isinstance(val, HTML):
            out[key] = str(val)
        elif isinstance(val, Markdown):
            out[key] = _markdown_to_html(str(val))
        else:
            out[key] = val
    return out
