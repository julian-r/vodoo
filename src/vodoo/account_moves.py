"""Accounting move (account.move) operations for Vodoo."""

from __future__ import annotations

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace


class _AccountMoveAttrs:
    """Shared account.move domain attributes."""

    _model: ClassVar[str] = "account.move"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "ref",
        "move_type",
        "state",
        "date",
        "invoice_date",
        "partner_id",
        "company_id",
        "currency_id",
        "amount_total",
    ]
    _default_detail_fields: ClassVar[list[str] | None] = [
        "id",
        "name",
        "ref",
        "move_type",
        "state",
        "date",
        "invoice_date",
        "invoice_date_due",
        "payment_state",
        "partner_id",
        "company_id",
        "currency_id",
        "amount_total",
        "amount_untaxed",
        "amount_tax",
        "invoice_origin",
        "invoice_user_id",
        "narration",
        "create_date",
        "write_date",
    ]
    _record_type: ClassVar[str] = "Account Move"


class AccountMoveNamespace(_AccountMoveAttrs, DomainNamespace):
    """Namespace for ``account.move`` operations."""


def build_account_move_domain(
    *,
    search: str | None = None,
    company: str | None = None,
    company_id: int | None = None,
    partner: str | None = None,
    move_type: str | None = None,
    state: str | None = None,
    year: int | None = None,
) -> list[Any]:
    """Build a domain for account.move list filtering."""
    domain: list[Any] = []

    if search:
        search_fields = ["name", "ref", "payment_reference", "invoice_origin"]
        for _ in range(len(search_fields) - 1):
            domain.append("|")
        for field in search_fields:
            domain.append((field, "ilike", search))

    if company:
        domain.append(("company_id.name", "ilike", company))
    if company_id is not None:
        domain.append(("company_id", "=", company_id))
    if partner:
        domain.append(("partner_id.name", "ilike", partner))
    if move_type:
        domain.append(("move_type", "=", move_type))
    if state:
        domain.append(("state", "=", state))
    if year is not None:
        date_from = f"{year:04d}-01-01"
        date_to = f"{year:04d}-12-31"
        domain.append(("date", ">=", date_from))
        domain.append(("date", "<=", date_to))

    return domain


__all__ = ["AccountMoveNamespace", "build_account_move_domain"]
