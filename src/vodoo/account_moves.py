"""Accounting move (account.move) operations for Vodoo."""

from __future__ import annotations

from typing import Any

from vodoo.generated.account_moves import GeneratedAccountMoveNamespace


class AccountMoveNamespace(GeneratedAccountMoveNamespace):
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
