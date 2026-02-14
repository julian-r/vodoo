"""Async knowledge article operations for Vodoo."""

from typing import Any

from vodoo.aio.base import (
    _get_console,
    _html_to_markdown,
    _is_simple_output,
    display_records,
    get_record,
    get_record_url,
    list_fields,
    list_records,
    set_record_fields,
)
from vodoo.aio.base import (
    add_comment as base_add_comment,
)
from vodoo.aio.base import (
    add_note as base_add_note,
)
from vodoo.aio.base import (
    create_attachment as base_create_attachment,
)
from vodoo.aio.base import (
    list_attachments as base_list_attachments,
)
from vodoo.aio.base import (
    list_messages as base_list_messages,
)
from vodoo.aio.client import AsyncOdooClient

MODEL = "knowledge.article"


async def list_articles(
    client: AsyncOdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List knowledge articles."""
    if fields is None:
        fields = ["id", "name", "parent_id", "category", "icon", "write_date"]
    return await list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_articles(articles: list[dict[str, Any]]) -> None:
    """Display knowledge articles in a table."""
    display_records(articles, title="Knowledge Articles")


async def get_article(
    client: AsyncOdooClient, article_id: int, fields: list[str] | None = None
) -> dict[str, Any]:
    """Get a knowledge article."""
    if fields is None:
        fields = ["id", "name", "parent_id", "category", "icon", "body", "write_date"]
    return await get_record(client, MODEL, article_id, fields=fields)


async def list_article_fields(client: AsyncOdooClient) -> dict[str, Any]:
    """List knowledge article fields."""
    return await list_fields(client, MODEL)


async def set_article_fields(
    client: AsyncOdooClient, article_id: int, values: dict[str, Any]
) -> bool:
    """Set knowledge article fields."""
    return await set_record_fields(client, MODEL, article_id, values)


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


async def add_comment(
    client: AsyncOdooClient,
    article_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a comment to a knowledge article."""
    return await base_add_comment(
        client, MODEL, article_id, message, user_id=user_id, markdown=markdown
    )


async def add_note(
    client: AsyncOdooClient,
    article_id: int,
    message: str,
    user_id: int | None = None,
    markdown: bool = True,
) -> bool:
    """Add a note to a knowledge article."""
    return await base_add_note(
        client, MODEL, article_id, message, user_id=user_id, markdown=markdown
    )


async def list_article_messages(
    client: AsyncOdooClient, article_id: int, limit: int | None = None
) -> list[dict[str, Any]]:
    """List knowledge article messages."""
    return await base_list_messages(client, MODEL, article_id, limit=limit)


async def list_article_attachments(
    client: AsyncOdooClient, article_id: int
) -> list[dict[str, Any]]:
    """List knowledge article attachments."""
    return await base_list_attachments(client, MODEL, article_id)


async def create_article_attachment(
    client: AsyncOdooClient,
    article_id: int,
    file_path: Any,
    name: str | None = None,
) -> int:
    """Create a knowledge article attachment."""
    return await base_create_attachment(client, MODEL, article_id, file_path, name=name)


async def get_article_url(client: AsyncOdooClient, article_id: int) -> str:
    """Get the web URL for a knowledge article."""
    article = await get_article(client, article_id, fields=["article_url"])
    if article.get("article_url"):
        return str(article["article_url"])
    return get_record_url(client, MODEL, article_id)
