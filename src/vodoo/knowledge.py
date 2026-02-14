"""Knowledge article operations for Vodoo."""

from typing import Any

from vodoo.base import (
    _get_console,
    _html_to_markdown,
    _is_simple_output,
    get_record,
    get_record_url,
    list_fields,
    list_records,
    set_record_fields,
)
from vodoo.base import (
    add_comment as base_add_comment,
)
from vodoo.base import (
    add_note as base_add_note,
)
from vodoo.base import (
    create_attachment as base_create_attachment,
)
from vodoo.base import (
    list_attachments as base_list_attachments,
)
from vodoo.base import (
    list_messages as base_list_messages,
)
from vodoo.client import OdooClient

MODEL = "knowledge.article"

# Default fields for list operations
DEFAULT_LIST_FIELDS = ["id", "name", "parent_id", "category", "icon", "write_date"]

# Default fields for get (detail) operations
DEFAULT_DETAIL_FIELDS = ["id", "name", "parent_id", "category", "icon", "body", "write_date"]


def list_articles(
    client: OdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List knowledge articles."""
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)
    return list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_articles(articles: list[dict[str, Any]]) -> None:
    """Display knowledge articles in a table."""
    from vodoo.base import display_records

    display_records(articles, title="Knowledge Articles")


def get_article(
    client: OdooClient, article_id: int, fields: list[str] | None = None
) -> dict[str, Any]:
    """Get a knowledge article."""
    if fields is None:
        fields = list(DEFAULT_DETAIL_FIELDS)
    return get_record(client, MODEL, article_id, fields=fields)


def list_article_fields(client: OdooClient) -> dict[str, Any]:
    """List knowledge article fields."""
    return list_fields(client, MODEL)


def set_article_fields(client: OdooClient, article_id: int, values: dict[str, Any]) -> bool:
    """Set knowledge article fields."""
    return set_record_fields(client, MODEL, article_id, values)


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


def add_comment(
    client: OdooClient,
    article_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a knowledge article."""
    return base_add_comment(client, MODEL, article_id, message, user_id=user_id, markdown=markdown)


def add_note(
    client: OdooClient,
    article_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a note to a knowledge article."""
    return base_add_note(client, MODEL, article_id, message, user_id=user_id, markdown=markdown)


def list_article_messages(
    client: OdooClient, article_id: int, limit: int | None = None
) -> list[dict[str, Any]]:
    """List knowledge article messages."""
    return base_list_messages(client, MODEL, article_id, limit=limit)


def list_article_attachments(client: OdooClient, article_id: int) -> list[dict[str, Any]]:
    """List knowledge article attachments."""
    return base_list_attachments(client, MODEL, article_id)


def create_article_attachment(
    client: OdooClient,
    article_id: int,
    file_path: Any,
    name: str | None = None,
) -> int:
    """Create a knowledge article attachment."""
    return base_create_attachment(client, MODEL, article_id, file_path, name=name)


def get_article_url(client: OdooClient, article_id: int) -> str:
    """Get the web URL for a knowledge article."""
    article = get_article(client, article_id, fields=["article_url"])
    if article.get("article_url"):
        return str(article["article_url"])
    # Fallback to standard URL format
    return get_record_url(client, MODEL, article_id)
