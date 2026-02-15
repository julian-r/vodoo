"""Async CRM lead/opportunity operations for Vodoo."""

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.crm import _CRMAttrs


class AsyncCRMNamespace(_CRMAttrs, AsyncDomainNamespace):
    """Async CRM leads/opportunities namespace."""


__all__ = ["AsyncCRMNamespace"]
