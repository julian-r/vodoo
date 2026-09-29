"""Compatibility alias for the CLI moved to :mod:`vodoo.cli.app`."""

import sys

from vodoo.cli import app as _app_module

# Preserve monkeypatching and imports through ``vodoo.main`` while keeping the
# implementation and its Typer/Rich dependencies inside the CLI package.
sys.modules[__name__] = _app_module
