"""Tests for knowledge article helpers and namespaces."""

from __future__ import annotations

import asyncio
from typing import Any

from vodoo.aio.knowledge import AsyncKnowledgeNamespace
from vodoo.content import Markdown
from vodoo.knowledge import KnowledgeNamespace, _build_article_values


class _StubClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []

    def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        self.calls.append((model, values, context))
        return 101


class _StubAsyncClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []

    async def create(
        self,
        model: str,
        values: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> int:
        self.calls.append((model, values, context))
        return 202


class TestBuildArticleValues:
    def test_build_values_with_optional_fields(self) -> None:
        values = _build_article_values(
            "Runbook",
            body="# Hello",
            parent_id=33,
            category="workspace",
            icon="📘",
            x_custom_field="abc",
        )

        assert values["name"] == "Runbook"
        assert isinstance(values["body"], Markdown)
        assert str(values["body"]) == "# Hello"
        assert values["parent_id"] == 33
        assert values["category"] == "workspace"
        assert values["icon"] == "📘"
        assert values["x_custom_field"] == "abc"


class TestKnowledgeNamespaceCreate:
    def test_sync_create_calls_client_create(self) -> None:
        client = _StubClient()
        namespace = KnowledgeNamespace(client=client)  # type: ignore[arg-type]

        article_id = namespace.create(
            "Team Handbook",
            body="## Intro",
            category="workspace",
        )

        assert article_id == 101
        assert len(client.calls) == 1
        model, values, context = client.calls[0]
        assert model == "knowledge.article"
        assert context is None
        assert values["name"] == "Team Handbook"
        assert isinstance(values["body"], Markdown)
        assert values["category"] == "workspace"

    def test_async_create_calls_client_create(self) -> None:
        client = _StubAsyncClient()
        namespace = AsyncKnowledgeNamespace(client=client)  # type: ignore[arg-type]

        article_id = asyncio.run(
            namespace.create(
                "Async Handbook",
                body="Async body",
                parent_id=12,
            )
        )

        assert article_id == 202
        assert len(client.calls) == 1
        model, values, context = client.calls[0]
        assert model == "knowledge.article"
        assert context is None
        assert values["name"] == "Async Handbook"
        assert isinstance(values["body"], Markdown)
        assert values["parent_id"] == 12
