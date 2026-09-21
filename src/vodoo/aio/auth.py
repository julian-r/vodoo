"""Async authentication utilities for Vodoo.

Mirrors :mod:`vodoo.auth` with async methods.
"""

from typing import Any

from vodoo.aio.client import AsyncOdooClient
from vodoo.exceptions import ConfigurationError, RecordNotFoundError


async def get_default_user_id(client: AsyncOdooClient, username: str | None = None) -> int:
    """Get the default requested-author user ID for message operations.

    Args:
        client: Async Odoo client
        username: Username to search for (defaults to configured username)

    Returns:
        User ID

    Raises:
        RecordNotFoundError: If user not found
    """
    search_username = username or client.username
    user_ids = await client.search("res.users", domain=[("login", "=", search_username)], limit=1)
    if not user_ids:
        raise RecordNotFoundError("res.users", 0)
    return user_ids[0]


async def get_partner_id_from_user(client: AsyncOdooClient, user_id: int) -> int:
    """Get the partner ID associated with a user.

    Args:
        client: Async Odoo client
        user_id: User ID (res.users)

    Returns:
        Partner ID (res.partner)

    Raises:
        RecordNotFoundError: If user not found or has no partner
    """
    users = await client.read("res.users", [user_id], ["partner_id"])
    if not users:
        raise RecordNotFoundError("res.users", user_id)

    partner_id = users[0].get("partner_id")
    if not partner_id:
        raise RecordNotFoundError("res.partner", 0)

    if isinstance(partner_id, list):
        result: int = partner_id[0]
        return result
    return int(partner_id)


async def message_post_sudo(
    client: AsyncOdooClient,
    model: str,
    res_id: int,
    body: str,
    user_id: int | None = None,
    message_type: str = "comment",
    is_note: bool = False,
    **kwargs: Any,
) -> bool:
    """Post a message or note requesting a specific displayed author.

    Cross-user attribution requires an internal authenticated user. Odoo may reject or
    override it for share users, which can reliably attribute only to their own partner.
    This does not change the authenticated identity, access checks, or auditing.

    Returns:
        True if successful
    """
    message_id = await message_post_sudo_with_id(
        client,
        model,
        res_id,
        body,
        user_id=user_id,
        message_type=message_type,
        is_note=is_note,
        **kwargs,
    )
    return bool(message_id)


async def message_post_sudo_with_id(
    client: AsyncOdooClient,
    model: str,
    res_id: int,
    body: str,
    user_id: int | None = None,
    message_type: str = "comment",
    is_note: bool = False,
    **kwargs: Any,
) -> int:
    """Post requesting a specific displayed author and return the message ID.

    Cross-user attribution requires an internal authenticated user. Odoo may reject or
    override it for share users, which can reliably attribute only to their own partner.
    This does not change the authenticated identity, access checks, or auditing.

    Args:
        client: Async Odoo client
        model: Model name (e.g., 'helpdesk.ticket')
        res_id: Record ID
        body: Message body (HTML)
        user_id: User whose partner is requested as author (uses default if None)
        message_type: Type of message ('comment' or 'notification')
        is_note: If True, creates an internal note
        **kwargs: Additional arguments for message_post

    Returns:
        ID of the created ``mail.message`` record

    Raises:
        ConfigurationError: If no default user configured
    """
    if user_id is None:
        if client.config.default_user_id is None:
            msg = "No default user ID configured"
            raise ConfigurationError(msg)
        user_id = client.config.default_user_id

    partner_id = await get_partner_id_from_user(client, user_id)

    subtype_xmlid = "mt_note" if is_note else "mt_comment"
    subtype_rows = await client.search_read(
        "ir.model.data",
        domain=[("module", "=", "mail"), ("name", "=", subtype_xmlid)],
        fields=["res_id"],
        limit=1,
    )
    subtype_id = subtype_rows[0].get("res_id") if subtype_rows else None
    if not isinstance(subtype_id, int) or isinstance(subtype_id, bool) or subtype_id <= 0:
        raise RecordNotFoundError("mail.message.subtype", 0)

    effective_message_type = "notification" if is_note else message_type

    message_vals = {
        "model": model,
        "res_id": res_id,
        "body": body,
        "message_type": effective_message_type,
        "subtype_id": subtype_id,
        "author_id": partner_id,
        **kwargs,
    }

    return await client.create("mail.message", message_vals)
