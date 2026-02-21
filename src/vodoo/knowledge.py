"""Knowledge article operations for Vodoo."""

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.base import (
    _get_console,
    _html_to_markdown,
    _is_simple_output,
)
from vodoo.content import Markdown


class _KnowledgeAttrs:
    _model = "knowledge.article"
    _default_fields: ClassVar[list[str]] = [
        "id",
        "name",
        "parent_id",
        "category",
        "icon",
        "write_date",
    ]
    _default_detail_fields: ClassVar[list[str] | None] = [
        "id",
        "name",
        "parent_id",
        "category",
        "icon",
        "body",
        "write_date",
    ]
    _record_type = "Article"


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
    values: dict[str, Any] = {"name": name, **extra_fields}
    if body is not None:
        values["body"] = Markdown(body)
    if parent_id is not None:
        values["parent_id"] = parent_id
    if category is not None:
        values["category"] = category
    if icon is not None:
        values["icon"] = icon
    return values


class KnowledgeNamespace(_KnowledgeAttrs, DomainNamespace):
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
    """Display detailed knowledge article information with body content."""
    if _is_simple_output():
        print(f"id: {article['id']}")
        print(f"name: {article.get('icon', '')} {article['name']}")
        if article.get("parent_id"):
            print(f"parent: {article['parent_id'][1]}")
        if article.get("category"):
            print(f"category: {article['category']}")
        if article.get("body"):
            body = article["body"] if show_html else _html_to_markdown(article["body"])
            print(f"body: {body}")
    else:
        console = _get_console()
        console.print(f"\n[bold cyan]Article #{article['id']}[/bold cyan]")
        console.print(f"[bold]Title:[/bold] {article.get('icon', '')} {article['name']}")

        if article.get("parent_id"):
            console.print(f"[bold]Parent:[/bold] {article['parent_id'][1]}")

        if article.get("category"):
            console.print(f"[bold]Category:[/bold] {article['category']}")

        if article.get("body"):
            body = article["body"]
            if show_html:
                console.print(f"\n[bold]Content:[/bold]\n{body}")
            else:
                markdown_text = _html_to_markdown(body)
                console.print(f"\n[bold]Content:[/bold]\n{markdown_text}")
