"""Async CRM lead/opportunity operations for Vodoo."""

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.crm import CRMNamespace


class AsyncCRMNamespace(AsyncDomainNamespace):
    """Async CRM leads/opportunities namespace."""

    _model = CRMNamespace._model
    _tag_model = CRMNamespace._tag_model
    _default_fields = CRMNamespace._default_fields
    _record_type = CRMNamespace._record_type


__all__ = ["AsyncCRMNamespace"]
