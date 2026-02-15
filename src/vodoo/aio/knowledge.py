"""Async knowledge article operations for Vodoo."""

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.knowledge import (
    KnowledgeNamespace,
)


class AsyncKnowledgeNamespace(AsyncDomainNamespace):
    """Async namespace for knowledge.article model."""

    _model = KnowledgeNamespace._model
    _default_fields = KnowledgeNamespace._default_fields
    _default_detail_fields = KnowledgeNamespace._default_detail_fields
    _record_type = KnowledgeNamespace._record_type

    async def url(self, record_id: int) -> str:  # type: ignore[override]
        """Get the web URL for a knowledge article.

        Tries the ``article_url`` field first, falls back to the standard URL.
        """
        article = await self.get(record_id, fields=["article_url"])
        if article.get("article_url"):
            return str(article["article_url"])
        return super().url(record_id)
