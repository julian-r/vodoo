"""Interactive Rich output renderer for the Vodoo CLI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rich.console import Console


@dataclass(slots=True)
class RichRenderer:
    """Render interactive output through a Rich console."""

    console: Console = field(default_factory=Console)
    mode: str = "rich"
    structured: bool = False

    def write(self, value: object = "", **kwargs: Any) -> None:
        """Render one value through Rich."""
        self.console.print(value, **kwargs)
