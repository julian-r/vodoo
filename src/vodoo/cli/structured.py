"""Machine-readable JSON and TOON output renderers."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Literal, TextIO

from toon_format import encode


@dataclass(slots=True)
class StructuredRenderer:
    """Render deterministic machine-readable output."""

    format: Literal["json", "toon"]
    stream: TextIO | None = None
    structured: bool = True

    @property
    def mode(self) -> str:
        """Return the configured output mode."""
        return self.format

    def write(self, value: Any) -> None:
        """Encode and write one value followed by a newline."""
        if self.format == "toon":
            rendered = encode(value)
        else:
            rendered = json.dumps(value, default=str, ensure_ascii=False)
        (self.stream or sys.stdout).write(f"{rendered}\n")
