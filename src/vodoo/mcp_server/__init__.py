"""MCP (Model Context Protocol) server for Vodoo.

Exposes Odoo records, accounting, chatter, attachments, and timers as MCP tools for
clients such as Claude Desktop. Requires the optional ``mcp`` extra::

    uvx --from 'vodoo[mcp]' vodoo mcp --allow-write
"""

from vodoo.mcp_server.server import create_server, run

__all__ = ["create_server", "run"]
