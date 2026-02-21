"""Async knowledge article operations for Vodoo."""

from typing import Any

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.knowledge import _build_article_values, _KnowledgeAttrs


class AsyncKnowledgeNamespace(_KnowledgeAttrs, AsyncDomainNamespace):
    """Async namespace for knowledge.article model."""

    async def create(
        self,
        name: str,
        *,
        body: str | None = None,
        parent_id: int | None = None,
        category: str | None = None,
        icon: str | None = None,
        **extra_fields: Any,
    ) -> int:
        """Create a knowledge article."""
        values = _build_article_values(
            name,
            body=body,
            parent_id=parent_id,
            category=category,
            icon=icon,
            **extra_fields,
        )
        return await self._client.create(self._model, values)

    async def url(self, record_id: int) -> str:  # type: ignore[override]
        """Get the web URL for a knowledge article.

        Tries the ``article_url`` field first, falls back to the standard URL.
        """
        article = await self.get(record_id, fields=["article_url"])
        if article.get("article_url"):
            return str(article["article_url"])
        return super().url(record_id)
