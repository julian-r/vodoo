"""Async CRM lead/opportunity operations for Vodoo."""

from typing import ClassVar

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.crm import display_lead_detail, display_leads


class AsyncCRMNamespace(AsyncDomainNamespace):
    """Async CRM leads/opportunities namespace."""

    _model: ClassVar[str] = "crm.lead"
    _tag_model: ClassVar[str | None] = "crm.tag"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "partner_id",
        "stage_id",
        "user_id",
        "team_id",
        "expected_revenue",
        "probability",
        "type",
        "priority",
        "tag_ids",
        "create_date",
    ]
    _record_type: ClassVar[str] = "Lead"


__all__ = ["AsyncCRMNamespace", "display_lead_detail", "display_leads"]
