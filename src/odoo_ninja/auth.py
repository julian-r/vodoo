"""Authentication utilities for Odoo Ninja."""

from typing import Any

from odoo_ninja.client import OdooClient


def get_default_user_id(client: OdooClient, username: str | None = None) -> int:
    """Get the default user ID for sudo operations.

    Args:
        client: Odoo client
        username: Username to search for (defaults to configured username)

    Returns:
        User ID

    Raises:
        ValueError: If user not found

    """
    search_username = username or client.username
    user_ids = client.search("res.users", domain=[("login", "=", search_username)], limit=1)

    if not user_ids:
        msg = f"User '{search_username}' not found"
        raise ValueError(msg)

    return user_ids[0]


def get_partner_id_from_user(client: OdooClient, user_id: int) -> int:
    """Get the partner ID associated with a user.

    In Odoo, res.users has a partner_id field that links to res.partner.
    The mail.message.author_id field references res.partner, not res.users.

    Args:
        client: Odoo client
        user_id: User ID (res.users)

    Returns:
        Partner ID (res.partner)

    Raises:
        ValueError: If user not found or has no partner

    """
    users = client.read("res.users", [user_id], ["partner_id"])
    if not users:
        msg = f"User {user_id} not found"
        raise ValueError(msg)

    partner_id = users[0].get("partner_id")
    if not partner_id:
        msg = f"User {user_id} has no associated partner"
        raise ValueError(msg)

    # partner_id is returned as [id, name] tuple
    if isinstance(partner_id, list):
        result: int = partner_id[0]
        return result
    return int(partner_id)


def message_post_sudo(
    client: OdooClient,
    model: str,
    res_id: int,
    body: str,
    user_id: int | None = None,
    message_type: str = "comment",
    is_note: bool = False,
    **kwargs: Any,
) -> bool:
    """Post a message or note as a specific user using sudo.

    Args:
        client: Odoo client
        model: Model name (e.g., 'helpdesk.ticket')
        res_id: Record ID
        body: Message body (HTML)
        user_id: User ID to post as (uses default if None)
        message_type: Type of message ('comment' or 'notification')
        is_note: If True, creates an internal note (not visible to customers)
        **kwargs: Additional arguments for message_post

    Returns:
        True if successful

    Raises:
        ValueError: If no default user configured

    """
    if user_id is None:
        if client.config.default_user_id is None:
            msg = "No default user ID configured"
            raise ValueError(msg)
        user_id = client.config.default_user_id

    # Convert user_id (res.users) to partner_id (res.partner)
    # mail.message.author_id references res.partner, not res.users
    partner_id = get_partner_id_from_user(client, user_id)

    # Create the message directly in mail.message model
    # This avoids the XML-RPC marshalling issue with message_post

    # For notes, we want the "Note" subtype, for comments we want "Discussions"
    subtype_name = "Note" if is_note else "Discussions"
    subtype_ids = client.search(
        "mail.message.subtype", domain=[("name", "=", subtype_name)], limit=1
    )

    message_vals = {
        "model": model,
        "res_id": res_id,
        "body": body,
        "message_type": message_type,
        "subtype_id": subtype_ids[0] if subtype_ids else False,
        "author_id": partner_id,  # Use partner_id, not user_id
        **kwargs,
    }

    # Create the message
    message_id = client.create("mail.message", message_vals)
    return bool(message_id)
