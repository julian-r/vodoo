"""Async knowledge article operations for Vodoo."""

from typing import Any

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
    display_records,
    get_record,
    get_record_url,
    list_fields,
    list_records,
    set_record_fields,
)
from vodoo.aio.base import (
    list_attachments as base_list_attachments,
)
from vodoo.aio.base import (
    list_messages as base_list_messages,
)
from vodoo.aio.client import AsyncOdooClient
from vodoo.knowledge import (
    DEFAULT_DETAIL_FIELDS,
    DEFAULT_LIST_FIELDS,
    MODEL,
)
from vodoo.knowledge import (
    display_article_detail as display_article_detail,
)


async def list_articles(
    client: AsyncOdooClient,
    domain: list[Any] | None = None,
    limit: int | None = 50,
    fields: list[str] | None = None,
) -> list[dict[str, Any]]:
    """List knowledge articles."""
    if fields is None:
        fields = list(DEFAULT_LIST_FIELDS)
    return await list_records(client, MODEL, domain=domain, limit=limit, fields=fields)


def display_articles(articles: list[dict[str, Any]]) -> None:
    """Display knowledge articles in a table."""
    display_records(articles, title="Knowledge Articles")


async def get_article(
    client: AsyncOdooClient, article_id: int, fields: list[str] | None = None
) -> dict[str, Any]:
    """Get a knowledge article."""
    if fields is None:
        fields = list(DEFAULT_DETAIL_FIELDS)
    return await get_record(client, MODEL, article_id, fields=fields)


async def list_article_fields(client: AsyncOdooClient) -> dict[str, Any]:
    """List knowledge article fields."""
    return await list_fields(client, MODEL)


async def set_article_fields(
    client: AsyncOdooClient, article_id: int, values: dict[str, Any]
) -> bool:
    """Set knowledge article fields."""
    return await set_record_fields(client, MODEL, article_id, values)


# display_article_detail is imported from vodoo.knowledge (pure function, no I/O)


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
