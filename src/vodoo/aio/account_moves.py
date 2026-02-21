"""Async account.move operations for Vodoo."""

from vodoo.account_moves import _AccountMoveAttrs
from vodoo.aio._domain import AsyncDomainNamespace


class AsyncAccountMoveNamespace(_AccountMoveAttrs, AsyncDomainNamespace):
    """Async namespace for ``account.move`` operations."""


__all__ = ["AsyncAccountMoveNamespace"]
