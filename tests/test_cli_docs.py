"""Tests for generated CLI reference documentation."""

from __future__ import annotations

import click

from scripts.gen_cli_docs import format_type


def test_variadic_argument_type_uses_ellipsis() -> None:
    argument = click.Argument(["blocked_by_ids"], type=int, nargs=-1, required=True)

    assert format_type(argument) == "INT..."
