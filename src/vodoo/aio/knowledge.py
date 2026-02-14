"""Async knowledge article operations for Vodoo."""

from typing import ClassVar

from vodoo.aio._domain import AsyncDomainNamespace
from vodoo.knowledge import (
    display_article_detail as display_article_detail,
)
from vodoo.knowledge import (
    display_articles as display_articles,
)


class AsyncKnowledgeNamespace(AsyncDomainNamespace):
    """Async namespace for knowledge.article model."""

    _model = "knowledge.article"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "parent_id",
        "category",
        "icon",
        "write_date",
    ]
    _default_detail_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "parent_id",
        "category",
        "icon",
        "body",
        "write_date",
    ]
    _record_type = "Article"

    async def url(self, record_id: int) -> str:  # type: ignore[override]
        """Get the web URL for a knowledge article.

        Tries the ``article_url`` field first, falls back to the standard URL.
        """
        article = await self.get(record_id, fields=["article_url"])
        if article.get("article_url"):
            return str(article["article_url"])
        return super().url(record_id)
