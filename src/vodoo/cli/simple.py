"""Plain-text output renderer for the Vodoo CLI."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(slots=True)
class SimpleRenderer:
    """Render deterministic line-oriented plain text."""

    stream: TextIO | None = None
    mode: str = "simple"
    structured: bool = False

    def write(self, value: object = "") -> None:
        """Write one value followed by a newline."""
        (self.stream or sys.stdout).write(f"{value}\n")
