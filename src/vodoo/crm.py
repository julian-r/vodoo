"""CRM lead/opportunity operations for Vodoo."""

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace


class CRMNamespace(DomainNamespace):
    """CRM leads/opportunities namespace."""

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


def display_leads(leads: list[dict[str, Any]]) -> None:
    """Display leads in a rich table.

    Args:
        leads: List of lead dictionaries

    """
    from vodoo.base import display_records

    display_records(leads, title="CRM Leads")


def display_lead_detail(lead: dict[str, Any], show_html: bool = False) -> None:
    """Display detailed lead information.

    Args:
        lead: Lead dictionary
        show_html: If True, show raw HTML description, else convert to markdown

    """
    from vodoo.base import display_record_detail

    display_record_detail(lead, show_html=show_html, record_type="Lead")
