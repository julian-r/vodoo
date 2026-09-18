"""Async account.move operations for Vodoo."""

from vodoo.aio.generated.account_moves import GeneratedAsyncAccountMoveNamespace


class AsyncAccountMoveNamespace(GeneratedAsyncAccountMoveNamespace):
    """Async namespace for ``account.move`` operations."""


__all__ = ["AsyncAccountMoveNamespace"]
