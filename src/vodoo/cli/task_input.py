"""Description input shared by task CLI commands (no content conversion)."""

from __future__ import annotations

import sys
from pathlib import Path

from vodoo.exceptions import FieldParsingError


def load_description(inline: str | None, description_file: Path | None) -> str | None:
    """Load verbatim UTF-8 text from PATH or ``-`` (stdin), or return inline text.

    Raises :class:`FieldParsingError` for conflicting inputs, unreadable input,
    or invalid UTF-8. Call before any mutation. Markdown/HTML conversion remains
    the caller's responsibility, exactly as for an inline description.
    """
    if inline is not None and description_file is not None:
        raise FieldParsingError("Inline description and --description-file are mutually exclusive")
    if description_file is None:
        return inline

    try:
        if description_file == Path("-"):
            # Decode explicitly rather than depending on the terminal's locale.
            buffer = getattr(sys.stdin, "buffer", None)
            if buffer is not None:
                return bytes(buffer.read()).decode("utf-8")
            # Text-only streams (e.g. StringIO) have already been decoded.
            return sys.stdin.read()
        return description_file.read_bytes().decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise FieldParsingError(
            f"Cannot read UTF-8 description from {description_file}: {exc}"
        ) from exc
