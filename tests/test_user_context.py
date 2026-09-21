"""The user-context helper must not claim authentication impersonation."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

from vodoo.aio.client import AsyncOdooClient
from vodoo.client import OdooClient


def test_sync_user_context_helper_and_legacy_alias_merge_context() -> None:
    client = object.__new__(OdooClient)
    execute = MagicMock(return_value=True)
    client.execute = execute

    assert client.execute_with_user_context(
        "res.partner", "custom", 9, [1], context={"lang": "en_US"}
    )
    execute.assert_called_once_with(
        "res.partner",
        "custom",
        [1],
        context={"lang": "en_US", "sudo_user_id": 9},
    )

    execute.reset_mock()
    assert client.execute_sudo("res.partner", "custom", 9, [1])
    execute.assert_called_once_with("res.partner", "custom", [1], context={"sudo_user_id": 9})


def test_async_user_context_helper_and_legacy_alias_merge_context() -> None:
    async def exercise() -> None:
        client = object.__new__(AsyncOdooClient)
        execute = AsyncMock(return_value=True)
        client.execute = execute

        assert await client.execute_with_user_context(
            "res.partner", "custom", 9, [1], context={"lang": "en_US"}
        )
        execute.assert_awaited_once_with(
            "res.partner",
            "custom",
            [1],
            context={"lang": "en_US", "sudo_user_id": 9},
        )

        execute.reset_mock()
        assert await client.execute_sudo("res.partner", "custom", 9, [1])
        execute.assert_awaited_once_with("res.partner", "custom", [1], context={"sudo_user_id": 9})

    asyncio.run(exercise())
