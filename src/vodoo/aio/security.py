"""Async security group utilities for Vodoo."""

from typing import Any

from vodoo.aio.client import AsyncOdooClient
from vodoo.security import (
    GROUP_DEFINITIONS,
    AccessDefinition,
    GroupDefinition,
    RuleDefinition,
    _access_name,
    _rule_name,
)


async def _groups_field(client: AsyncOdooClient) -> str:
    """Return the many2many field name for user groups."""
    fields = await client.execute(
        "res.users", "fields_get", ["group_ids"], {"attributes": ["type"]}
    )
    if fields and "group_ids" in fields and fields["group_ids"].get("type") == "many2many":
        return "group_ids"
    return "groups_id"


async def create_security_groups(
    client: AsyncOdooClient,
) -> tuple[dict[str, int], list[str]]:
    """Create (or reuse) all Vodoo security groups."""
    warnings: list[str] = []
    group_ids: dict[str, int] = {}

    for group in GROUP_DEFINITIONS:
        group_id = await _ensure_group(client, group)
        group_ids[group.name] = group_id

        for access in group.access:
            model_id = await _get_model_id(client, access.model)
            if model_id is None:
                warnings.append(f"Model '{access.model}' not found; skipping access")
                continue
            await _ensure_access(client, group_id, group.name, model_id, access)

        for rule in group.rules:
            model_id = await _get_model_id(client, rule.model)
            if model_id is None:
                warnings.append(f"Model '{rule.model}' not found; skipping rule")
                continue
            await _ensure_rule(client, group_id, group.name, model_id, rule)

    return group_ids, warnings


async def get_group_ids(
    client: AsyncOdooClient,
    group_names: list[str],
) -> tuple[dict[str, int], list[str]]:
    """Fetch group IDs for the provided names."""
    warnings: list[str] = []
    group_ids: dict[str, int] = {}

    for name in group_names:
        ids = await client.search("res.groups", domain=[("name", "=", name)], limit=1)
        if ids:
            group_ids[name] = ids[0]
        else:
            warnings.append(f"Group '{name}' not found")

    return group_ids, warnings


async def assign_user_to_groups(
    client: AsyncOdooClient,
    user_id: int,
    group_ids: list[int],
    *,
    remove_default_groups: bool = True,
) -> None:
    """Assign a user to the provided groups."""
    commands: list[tuple[int, int]] = []

    if remove_default_groups:
        for xmlid in ("base.group_user", "base.group_portal"):
            gid = await _get_group_id_by_xmlid(client, xmlid)
            if gid is not None:
                commands.append((3, gid))

    commands.extend((4, gid) for gid in group_ids)

    field = await _groups_field(client)
    await client.write("res.users", [user_id], {field: commands})


async def resolve_user_id(
    client: AsyncOdooClient, *, user_id: int | None, login: str | None
) -> int:
    """Resolve a user ID from either an ID or login name."""
    if user_id is not None:
        return user_id
    if not login:
        raise ValueError("Provide --user-id or --login")

    ids = await client.search("res.users", domain=[("login", "=", login)], limit=1)
    if not ids:
        raise ValueError(f"User with login '{login}' not found")
    return ids[0]


async def _ensure_group(client: AsyncOdooClient, group: GroupDefinition) -> int:
    group_ids = await client.search("res.groups", domain=[("name", "=", group.name)], limit=1)
    if group_ids:
        return group_ids[0]
    return await client.create("res.groups", {"name": group.name, "comment": group.comment})


async def _ensure_access(
    client: AsyncOdooClient,
    group_id: int,
    group_name: str,
    model_id: int,
    access: AccessDefinition,
) -> int:
    name = _access_name(group_name, access.model)
    existing = await client.search(
        "ir.model.access",
        domain=[("name", "=", name), ("model_id", "=", model_id), ("group_id", "=", group_id)],
        limit=1,
    )
    if existing:
        return existing[0]

    return await client.create(
        "ir.model.access",
        {
            "name": name,
            "model_id": model_id,
            "group_id": group_id,
            "perm_read": access.perm_read,
            "perm_write": access.perm_write,
            "perm_create": access.perm_create,
            "perm_unlink": access.perm_unlink,
        },
    )


async def _ensure_rule(
    client: AsyncOdooClient,
    group_id: int,
    group_name: str,
    model_id: int,
    rule: RuleDefinition,
) -> int:
    name = _rule_name(group_name, rule.model)
    existing = await client.search(
        "ir.rule",
        domain=[("name", "=", name), ("model_id", "=", model_id)],
        limit=1,
    )
    if existing:
        return existing[0]

    return await client.create(
        "ir.rule",
        {
            "name": name,
            "model_id": model_id,
            "groups": [(4, group_id)],
            "domain_force": rule.domain,
            "perm_read": rule.perm_read,
            "perm_write": rule.perm_write,
            "perm_create": rule.perm_create,
            "perm_unlink": rule.perm_unlink,
        },
    )


async def _get_model_id(client: AsyncOdooClient, model: str) -> int | None:
    ids = await client.search("ir.model", domain=[("model", "=", model)], limit=1)
    if not ids:
        return None
    return ids[0]


async def _get_group_id_by_xmlid(client: AsyncOdooClient, xmlid: str) -> int | None:
    module, name = xmlid.split(".", maxsplit=1)
    records = await client.search_read(
        "ir.model.data",
        domain=[("module", "=", module), ("name", "=", name)],
        fields=["res_id"],
        limit=1,
    )
    if not records:
        return None
    return int(records[0]["res_id"])


async def create_user(
    client: AsyncOdooClient,
    name: str,
    login: str,
    password: str | None = None,
    email: str | None = None,
) -> tuple[int, str]:
    """Create a new user."""
    import secrets
    import string

    if password is None:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(secrets.choice(alphabet) for _ in range(24))

    if email is None:
        email = login

    field = await _groups_field(client)
    user_id = await client.create(
        "res.users",
        {
            "name": name,
            "login": login,
            "email": email,
            "password": password,
            field: [(6, 0, [])],
        },
    )

    return user_id, password


async def set_user_password(
    client: AsyncOdooClient,
    user_id: int,
    password: str | None = None,
) -> str:
    """Set a user's password."""
    import secrets
    import string

    if password is None:
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        password = "".join(secrets.choice(alphabet) for _ in range(24))

    await client.write("res.users", [user_id], {"password": password})
    return password


async def get_user_info(client: AsyncOdooClient, user_id: int) -> dict[str, Any]:
    """Get user information."""
    field = await _groups_field(client)
    users = await client.search_read(
        "res.users",
        domain=[("id", "=", user_id)],
        fields=["name", "login", "email", "active", "share", field, "partner_id"],
        limit=1,
    )
    if not users:
        raise ValueError(f"User {user_id} not found")
    return users[0]
