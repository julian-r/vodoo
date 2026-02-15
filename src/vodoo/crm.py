"""CRM lead/opportunity operations for Vodoo."""

from typing import ClassVar

from vodoo._domain import DomainNamespace


class _CRMAttrs:
    """Shared CRM domain attributes."""

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


class CRMNamespace(_CRMAttrs, DomainNamespace):
    """CRM leads/opportunities namespace."""
