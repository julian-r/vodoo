"""Async API for Vodoo.

Provides async versions of all Vodoo library components::

    from vodoo.aio import AsyncOdooClient
    from vodoo import OdooConfig

    config = OdooConfig(
        url="https://my-instance.odoo.com",
        database="mydb",
        username="bot@example.com",
        password="secret",
    )

    async with AsyncOdooClient(config) as client:
        # Use domain namespaces
        tickets = await client.helpdesk.list(limit=10)

        # Or the generic client directly
        partners = await client.search_read("res.partner", fields=["name", "email"], limit=5)
"""

from vodoo.aio.client import AsyncOdooClient

__all__ = [
    "AsyncOdooClient",
]
