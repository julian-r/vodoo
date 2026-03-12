"""Async CRM lead/opportunity operations for Vodoo."""

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.crm import _PIPELINE_FIELDS, STAGE_FIELDS, _CRMAttrs, build_pipeline_summary


class AsyncCRMNamespace(_CRMAttrs, AsyncDomainNamespace):
    """Async CRM leads/opportunities namespace."""

    async def create(
        self,
        name: str,
        *,
        partner_id: int | None = None,
        expected_revenue: float | None = None,
        stage_id: int | None = None,
        user_id: int | None = None,
        team_id: int | None = None,
        tag_ids: list[int] | None = None,
        lead_type: str = "opportunity",
        **extra_fields: Any,
    ) -> int:
        """Create a CRM lead or opportunity."""
        values: dict[str, Any] = {"name": name, "type": lead_type, **extra_fields}
        if partner_id is not None:
            values["partner_id"] = partner_id
        if expected_revenue is not None:
            values["expected_revenue"] = expected_revenue
        if stage_id is not None:
            values["stage_id"] = stage_id
        if user_id is not None:
            values["user_id"] = user_id
        if team_id is not None:
            values["team_id"] = team_id
        if tag_ids is not None:
            values["tag_ids"] = [(6, 0, tag_ids)]
        return await self._client.create(self._model, values)

    async def stages(self, *, team_id: int | None = None) -> list[dict[str, Any]]:
        """List CRM pipeline stages."""
        domain: list[Any] = []
        if team_id is not None:
            domain.append(("team_id", "=", team_id))
        return await self._client.search_read(
            "crm.stage",
            domain=domain,
            fields=STAGE_FIELDS,
            order="sequence",
        )

    async def pipeline(
        self,
        *,
        team: str | None = None,
        user: str | None = None,
    ) -> dict[str, Any]:
        """Fetch pipeline data and return aggregated summary."""
        domain: list[Any] = [("type", "=", "opportunity")]
        if team:
            domain.append(("team_id.name", "ilike", team))
        if user:
            domain.append(("user_id.name", "ilike", user))

        deals = await self._client.search_read(
            self._model,
            domain=domain,
            fields=_PIPELINE_FIELDS,
            limit=0,
        )

        stages = await self._client.search_read(
            "crm.stage",
            domain=[],
            fields=STAGE_FIELDS,
            order="sequence",
        )

        return build_pipeline_summary(deals, stages, team=team)


__all__ = ["AsyncCRMNamespace"]
