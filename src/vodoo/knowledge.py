"""Knowledge article operations for Vodoo."""

from typing import Any, ClassVar

from vodoo._domain import DomainNamespace
from vodoo.base import (
    _get_console,
    _html_to_markdown,
    _is_simple_output,
)


class KnowledgeNamespace(DomainNamespace):
    """Namespace for knowledge.article model."""

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
