"""Knowledge article operations for Vodoo."""

from typing import Any

from vodoo.content import Markdown
from vodoo.generated.knowledge import GeneratedKnowledgeNamespace


def _build_article_values(
    name: str,
    *,
    body: str | None = None,
    parent_id: int | None = None,
    category: str | None = None,
    icon: str | None = None,
    **extra_fields: Any,
) -> dict[str, Any]:
    """Build the values dict for knowledge.article creation."""
    values: dict[str, Any] = {**extra_fields, "name": name}
    if body is not None:
        values["body"] = Markdown(body)
    if parent_id is not None:
        values["parent_id"] = parent_id
    if category is not None:
        values["category"] = category
    if icon is not None:
        values["icon"] = icon
    return values


class KnowledgeNamespace(GeneratedKnowledgeNamespace):
    """Namespace for knowledge.article model."""

    def create(
        self,
        name: str,
        *,
        body: str | None = None,
        parent_id: int | None = None,
        category: str | None = None,
        icon: str | None = None,
        **extra_fields: Any,
    ) -> int:
        """Create a knowledge article.

        Args:
            name: Article title/name.
            body: Article body as markdown text (converted to HTML).
            parent_id: Parent article ID.
            category: Article category (workspace/private/shared).
            icon: Emoji/icon for the article.
            **extra_fields: Additional fields to set on the article.

        Returns:
            ID of created article.
        """
        values = _build_article_values(
            name,
            body=body,
            parent_id=parent_id,
            category=category,
            icon=icon,
            **extra_fields,
        )
        return self._client.create(self._model, values)

    def url(self, record_id: int) -> str:
        """Get the web URL for a knowledge article.

        Tries the ``article_url`` field first, falls back to the standard URL.
        """
        article = self.get(record_id, fields=["article_url"])
        if article.get("article_url"):
            return str(article["article_url"])
        return super().url(record_id)


def display_article_detail(article: dict[str, Any], show_html: bool = False) -> None:
    """Deprecated compatibility shim for CLI article rendering."""
    from vodoo.cli.display import display_article_detail as render

    render(article, show_html)
