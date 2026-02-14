"""Security group utilities for Vodoo."""

import secrets
import string
from dataclasses import dataclass
from typing import Any

from vodoo.client import OdooClient


def _generate_password() -> str:
    """Generate a random 24-character password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(24))


@dataclass(frozen=True)
class AccessDefinition:
    """Access control entry for a model."""

    model: str
    perm_read: bool
    perm_write: bool
    perm_create: bool
    perm_unlink: bool


@dataclass(frozen=True)
class RuleDefinition:
    """Record rule definition for a model."""

    model: str
    domain: str
    perm_read: bool
    perm_write: bool
    perm_create: bool
    perm_unlink: bool


@dataclass(frozen=True)
class GroupDefinition:
    """Security group definition."""

    name: str
    comment: str
    access: tuple[AccessDefinition, ...]
    rules: tuple[RuleDefinition, ...] = ()


GROUP_DEFINITIONS: tuple[GroupDefinition, ...] = (
    GroupDefinition(
        name="API Mail Gateway",
        comment="Standalone access for mail gateway (message_process via XML-RPC)",
        access=(
            # Core mail routing (message_process, message_route)
            AccessDefinition("mail.message", True, False, False, False),
            AccessDefinition("mail.message.subtype", True, False, False, False),
            AccessDefinition("mail.alias", True, True, False, False),
            AccessDefinition("mail.alias.domain", True, False, False, False),
            # Author/user resolution (_mail_find_user_for_gateway, _mail_find_partner_from_emails)
            AccessDefinition("mail.followers", True, False, False, False),
            AccessDefinition("res.users", True, False, False, False),
            AccessDefinition("res.partner", True, False, False, False),
            # Model/data lookups (routing, _xmlid_to_res_id for subtypes)
            AccessDefinition("ir.model", True, False, False, False),
            AccessDefinition("ir.model.data", True, False, False, False),
        ),
    ),
    GroupDefinition(
        name="API Base",
        comment="Core API access - required for all service accounts",
        access=(
            AccessDefinition("res.company", True, False, False, False),
            AccessDefinition("res.users", True, False, False, False),
            AccessDefinition("res.partner", True, False, False, False),
            AccessDefinition("res.currency", True, False, False, False),
            AccessDefinition("res.country", True, False, False, False),
            AccessDefinition("res.country.state", True, False, False, False),
            AccessDefinition("ir.attachment", True, True, True, False),
            AccessDefinition("mail.message", True, True, True, False),
            AccessDefinition("mail.message.subtype", True, False, False, False),
            AccessDefinition("mail.followers", True, True, True, False),
            AccessDefinition("mail.notification", True, True, True, False),
        ),
        rules=(
            RuleDefinition("mail.message", "[(1, '=', 1)]", True, True, True, False),
            RuleDefinition("mail.followers", "[(1, '=', 1)]", True, True, True, False),
            RuleDefinition("mail.notification", "[(1, '=', 1)]", True, True, True, False),
        ),
    ),
    GroupDefinition(
        name="API CRM",
        comment="CRM leads and opportunities",
        access=(
            AccessDefinition("crm.lead", True, True, True, False),
            AccessDefinition("crm.tag", True, True, True, False),
            AccessDefinition("crm.stage", True, False, False, False),
            AccessDefinition("crm.team", True, False, False, False),
            AccessDefinition("utm.source", True, False, False, False),
            AccessDefinition("utm.medium", True, False, False, False),
            AccessDefinition("utm.campaign", True, False, False, False),
        ),
        rules=(RuleDefinition("crm.lead", "[(1, '=', 1)]", True, True, True, False),),
    ),
    GroupDefinition(
        name="API Project",
        comment="Projects and tasks (follower-based access)",
        access=(
            AccessDefinition("project.project", True, True, True, False),
            AccessDefinition("project.task", True, True, True, False),
            AccessDefinition("project.task.type", True, False, False, False),
            AccessDefinition("project.tags", True, True, True, False),
            AccessDefinition("project.milestone", True, True, True, False),
        ),
        rules=(
            RuleDefinition(
                "project.project",
                "[('message_partner_ids', 'in', [user.partner_id.id])]",
                True,
                True,
                True,
                False,
            ),
            RuleDefinition(
                "project.task",
                "[('project_id.message_partner_ids', 'in', [user.partner_id.id])]",
                True,
                True,
                True,
                False,
            ),
        ),
    ),
    GroupDefinition(
        name="API Knowledge",
        comment="Knowledge base articles",
        access=(
            AccessDefinition("knowledge.article", True, True, True, False),
            AccessDefinition("knowledge.article.member", True, False, False, False),
        ),
        rules=(RuleDefinition("knowledge.article", "[(1, '=', 1)]", True, True, True, False),),
    ),
    GroupDefinition(
        name="API Helpdesk",
        comment="Helpdesk tickets",
        access=(
            AccessDefinition("helpdesk.ticket", True, True, True, False),
            AccessDefinition("helpdesk.tag", True, True, True, False),
            AccessDefinition("helpdesk.stage", True, False, False, False),
            AccessDefinition("helpdesk.team", True, False, False, False),
            AccessDefinition("helpdesk.ticket.type", True, False, False, False),
            AccessDefinition("helpdesk.sla", True, False, False, False),
        ),
        rules=(RuleDefinition("helpdesk.ticket", "[(1, '=', 1)]", True, True, True, False),),
    ),
)


def _access_name(group_name: str, model: str) -> str:
    return f"vodoo_{_slugify(group_name)}_access_{model.replace('.', '_')}"


def _rule_name(group_name: str, model: str) -> str:
    return f"vodoo_{_slugify(group_name)}_rule_{model.replace('.', '_')}"


def _slugify(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")


class SecurityNamespace:
    """Security group operations namespace."""

    def __init__(self, client: OdooClient) -> None:
        self._client = client

    def _groups_field(self) -> str:
        """Return the many2many field name for user groups.

        Odoo 19+ renamed ``groups_id`` → ``group_ids``.
        """
        fields = self._client.execute(
            "res.users", "fields_get", ["group_ids"], {"attributes": ["type"]}
        )
        if fields and "group_ids" in fields and fields["group_ids"].get("type") == "many2many":
            return "group_ids"
        return "groups_id"

    def create_groups(self) -> tuple[dict[str, int], list[str]]:
        """Create (or reuse) all Vodoo security groups.

        Returns:
            Tuple of group name -> group ID and a list of warnings.

        """
        warnings: list[str] = []
        group_ids: dict[str, int] = {}

        for group in GROUP_DEFINITIONS:
            group_id = self._ensure_group(group)
            group_ids[group.name] = group_id

            for access in group.access:
                model_id = self._get_model_id(access.model)
                if model_id is None:
                    warnings.append(f"Model '{access.model}' not found; skipping access")
                    continue
                self._ensure_access(group_id, group.name, model_id, access)

            for rule in group.rules:
                model_id = self._get_model_id(rule.model)
                if model_id is None:
                    warnings.append(f"Model '{rule.model}' not found; skipping rule")
                    continue
                self._ensure_rule(group_id, group.name, model_id, rule)

        return group_ids, warnings

    def get_group_ids(
        self,
        group_names: list[str],
    ) -> tuple[dict[str, int], list[str]]:
        """Fetch group IDs for the provided names.

        Args:
            group_names: Group names to resolve

        Returns:
            Tuple of group name -> group ID and a list of warnings.

        """
        warnings: list[str] = []
        group_ids: dict[str, int] = {}

        for name in group_names:
            ids = self._client.search("res.groups", domain=[("name", "=", name)], limit=1)
            if ids:
                group_ids[name] = ids[0]
            else:
                warnings.append(f"Group '{name}' not found")

        return group_ids, warnings

    def assign(
        self,
        user_id: int,
        group_ids: list[int],
        *,
        remove_default_groups: bool = True,
    ) -> None:
        """Assign a user to the provided groups.

        Args:
            user_id: User ID to update
            group_ids: Group IDs to add
            remove_default_groups: If True, remove base.group_user and base.group_portal first

        """
        commands: list[tuple[int, int]] = []

        if remove_default_groups:
            for xmlid in ("base.group_user", "base.group_portal"):
                group_id = self._get_group_id_by_xmlid(xmlid)
                if group_id is not None:
                    commands.append((3, group_id))

        commands.extend((4, group_id) for group_id in group_ids)

        self._client.write("res.users", [user_id], {self._groups_field(): commands})

    def resolve_user(self, *, user_id: int | None = None, login: str | None = None) -> int:
        """Resolve a user ID from either an ID or login name.

        Args:
            user_id: Explicit user ID
            login: User login/email

        Returns:
            User ID

        Raises:
            ValueError: If user not found

        """
        if user_id is not None:
            return user_id
        if not login:
            raise ValueError("Provide --user-id or --login")

        ids = self._client.search("res.users", domain=[("login", "=", login)], limit=1)
        if not ids:
            raise ValueError(f"User with login '{login}' not found")
        return ids[0]

    def create_user(
        self,
        name: str,
        login: str,
        password: str | None = None,
        email: str | None = None,
    ) -> tuple[int, str]:
        """Create a new user.

        Args:
            name: User's display name
            login: User's login (usually email)
            password: User's password (generated if not provided)
            email: User's email (defaults to login if not provided)

        Returns:
            Tuple of (user_id, password)

        """
        # Generate password if not provided
        if password is None:
            password = _generate_password()

        # Use login as email if not provided
        if email is None:
            email = login

        # Create user with no groups (share user, not billed)
        user_id = self._client.create(
            "res.users",
            {
                "name": name,
                "login": login,
                "email": email,
                "password": password,
                self._groups_field(): [(6, 0, [])],  # Empty groups = share user
            },
        )

        return user_id, password

    def set_password(
        self,
        user_id: int,
        password: str | None = None,
    ) -> str:
        """Set a user's password.

        Args:
            user_id: User ID
            password: New password (generated if not provided)

        Returns:
            The password that was set

        """
        # Generate password if not provided
        if password is None:
            password = _generate_password()

        self._client.write("res.users", [user_id], {"password": password})
        return password

    def get_user(self, user_id: int) -> dict[str, Any]:
        """Get user information.

        Args:
            user_id: User ID

        Returns:
            User information dictionary

        """
        users = self._client.search_read(
            "res.users",
            domain=[("id", "=", user_id)],
            fields=[
                "name",
                "login",
                "email",
                "active",
                "share",
                self._groups_field(),
                "partner_id",
            ],
            limit=1,
        )
        if not users:
            raise ValueError(f"User {user_id} not found")
        return users[0]

    def _ensure_group(self, group: GroupDefinition) -> int:
        group_ids = self._client.search("res.groups", domain=[("name", "=", group.name)], limit=1)
        if group_ids:
            return group_ids[0]
        return self._client.create("res.groups", {"name": group.name, "comment": group.comment})

    def _ensure_access(
        self,
        group_id: int,
        group_name: str,
        model_id: int,
        access: AccessDefinition,
    ) -> int:
        name = _access_name(group_name, access.model)
        existing = self._client.search(
            "ir.model.access",
            domain=[("name", "=", name), ("model_id", "=", model_id), ("group_id", "=", group_id)],
            limit=1,
        )
        if existing:
            return existing[0]

        return self._client.create(
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

    def _ensure_rule(
        self,
        group_id: int,
        group_name: str,
        model_id: int,
        rule: RuleDefinition,
    ) -> int:
        name = _rule_name(group_name, rule.model)
        existing = self._client.search(
            "ir.rule",
            domain=[("name", "=", name), ("model_id", "=", model_id)],
            limit=1,
        )
        if existing:
            return existing[0]

        return self._client.create(
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

    def _get_model_id(self, model: str) -> int | None:
        ids = self._client.search("ir.model", domain=[("model", "=", model)], limit=1)
        if not ids:
            return None
        return ids[0]

    def _get_group_id_by_xmlid(self, xmlid: str) -> int | None:
        module, name = xmlid.split(".", maxsplit=1)
        records = self._client.search_read(
            "ir.model.data",
            domain=[("module", "=", module), ("name", "=", name)],
            fields=["res_id"],
            limit=1,
        )
        if not records:
            return None
        return int(records[0]["res_id"])


# --- Backward-compatible free functions ---


def create_security_groups(client: OdooClient) -> tuple[dict[str, int], list[str]]:
    """Create (or reuse) all Vodoo security groups."""
    return SecurityNamespace(client).create_groups()


def get_group_ids(client: OdooClient, group_names: list[str]) -> tuple[dict[str, int], list[str]]:
    """Fetch group IDs for the provided names."""
    return SecurityNamespace(client).get_group_ids(group_names)


def assign_user_to_groups(
    client: OdooClient,
    user_id: int,
    group_ids: list[int],
    *,
    remove_default_groups: bool = True,
) -> None:
    """Assign a user to the provided groups."""
    SecurityNamespace(client).assign(
        user_id, group_ids, remove_default_groups=remove_default_groups
    )


def resolve_user_id(client: OdooClient, *, user_id: int | None, login: str | None) -> int:
    """Resolve a user ID from either an ID or login name."""
    return SecurityNamespace(client).resolve_user(user_id=user_id, login=login)


def create_user(
    client: OdooClient,
    name: str,
    login: str,
    password: str | None = None,
    email: str | None = None,
) -> tuple[int, str]:
    """Create a new user."""
    return SecurityNamespace(client).create_user(name, login, password=password, email=email)


def set_user_password(
    client: OdooClient,
    user_id: int,
    password: str | None = None,
) -> str:
    """Set a user's password."""
    return SecurityNamespace(client).set_password(user_id, password=password)


def get_user_info(client: OdooClient, user_id: int) -> dict[str, Any]:
    """Get user information."""
    return SecurityNamespace(client).get_user(user_id)
