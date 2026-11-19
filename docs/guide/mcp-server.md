# MCP Server (Claude Desktop)

Vodoo includes an [MCP](https://modelcontextprotocol.io) server. It gives Claude Desktop
(and other MCP clients such as Claude Code or Cursor) direct tools for your Odoo:
search and read any model, accounting (invoices, bills, journal entries, payments),
chatter, attachments, activities, and timers.

The server runs locally over stdio and uses your normal Vodoo configuration,
instance profiles, and keyring secrets. It works with Odoo 17, 18, and 19.

## Install in Claude Desktop

1. Configure Vodoo once (see [Configuration](../getting-started/configuration.md)) and
   check that it works: `uvx vodoo config test`.
2. In Claude Desktop, open **Settings → Developer → Edit Config**. This opens
   `claude_desktop_config.json`
   (macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`).
3. Add the server:

    ```json
    {
      "mcpServers": {
        "odoo": {
          "command": "/opt/homebrew/bin/uvx",
          "args": ["--from", "vodoo[mcp]", "vodoo", "mcp", "--allow-write"]
        }
      }
    }
    ```

4. Restart Claude Desktop. The Odoo tools appear in the tools menu.

!!! note "Use the full path to `uvx`"
    Claude Desktop does not use your shell's `PATH`. Run `which uvx` and put that path
    in `command` (often `/opt/homebrew/bin/uvx` or `~/.local/bin/uvx`).

### Options

| Argument | Effect |
|----------|--------|
| *(none)* | Read-only: search, read, accounting reports, chatter, attachments, timesheets. |
| `--allow-write` | Adds tools that create or change data (see below). |
| `--allow-delete` | Adds `delete_records` (permanent deletion). |
| `--instance NAME`, `-i NAME` | Use a named instance profile. |
| `--download-dir PATH` | The only folder downloads may go to (default `~/Downloads/vodoo`). |
| `--upload-dir PATH` | Folder whose files may be attached; repeat for more (default `~/Downloads`, `~/Desktop`, `~/Documents`). |

To use several Odoo instances, add one entry per instance:

```json
{
  "mcpServers": {
    "odoo-prod": {
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "vodoo[mcp]", "vodoo", "mcp", "-i", "prod", "--allow-write"]
    },
    "odoo-test": {
      "command": "/opt/homebrew/bin/uvx",
      "args": ["--from", "vodoo[mcp]", "vodoo", "mcp", "-i", "test", "--allow-write", "--allow-delete"]
    }
  }
}
```

You can also pass credentials as environment variables instead of a config file
(`"env": {"ODOO_URL": "...", "ODOO_DATABASE": "...", ...}`), but a config file or
keyring reference (`ODOO_PASSWORD_REF`) keeps the secret out of the Claude config.

### Other MCP clients

Any MCP client that starts stdio servers works the same way. For Claude Code:

```bash
claude mcp add odoo -- uvx --from 'vodoo[mcp]' vodoo mcp --allow-write
```

## Tools

### Read (always available)

| Tool | Purpose |
|------|---------|
| `odoo_info` | Connected instance, user, API, and enabled modes. |
| `search_records` | Search any model with a domain; paged, with total count. |
| `count_records` | Count records matching a domain. |
| `read_records` | Read records by id (curated detail fields, or all non-binary). |
| `get_fields` | Field metadata: type, label, relation, selection values. |
| `name_search` | Find ids by name (partners, products, accounts, taxes, journals). |
| `get_record_url` | Odoo web URL for a record. |
| `list_messages` | Chatter messages and notes (as Markdown). |
| `list_attachments` / `download_attachment` | Files on a record; download into the download folder. |
| `list_account_moves` | Invoices, bills, refunds, entries; filter by type, state, payment state, partner, dates, overdue. |
| `get_account_move` | One move with totals, status, and lines. |
| `list_timesheets` / `timer_status` | Your timesheets and running timers. |

### Write (`--allow-write`)

| Tool | Purpose |
|------|---------|
| `create_record` / `update_records` | Create or update records in any model. |
| `call_method` | Call a public model method (buttons/actions such as `action_confirm`). |
| `post_message` | Internal note (default) or public comment in the chatter. |
| `attach_file` | Upload a local file (from an allowed folder) to a record. |
| `create_account_move` | Draft invoice, bill, refund, or journal entry with lines (optionally post). |
| `post_account_moves` | Post (validate) moves. |
| `reset_account_moves_to_draft` / `cancel_account_moves` | Reset to draft / cancel. |
| `register_payment` | Odoo's *Register Payment* for posted invoices/bills (full or partial). |
| `mark_activity_done` | Mark an activity as done. |
| `timer_start` / `timer_stop` | Timers on tasks, tickets, or timesheets. |

### Delete (`--allow-delete`)

| Tool | Purpose |
|------|---------|
| `delete_records` | Permanently delete records. |

Without `--allow-delete`, the write tools also refuse to delete: `call_method` rejects
`unlink` methods, and values with the x2many delete command `[2, id, 0]` are refused.
Note that Odoo itself deletes one2many lines (for example invoice lines) that you remove
from a record you may edit.

## Safety

- The server is **read-only unless you pass `--allow-write`**. Deletion needs its own flag.
- All actions run as the configured Odoo user, with that user's access rights. Use a
  dedicated user or [service account](../cli/security.md) with only the rights you need.
- Tools carry MCP hints (read-only / destructive) so clients can ask for confirmation.
  In Claude Desktop, you approve each tool call, or allow a tool permanently.
- Posting assigns a final sequence number. Payments are real accounting entries.
  The server tells the model to confirm these with you first, but keep approvals on
  for `post_account_moves`, `register_payment`, `cancel_account_moves`, and `call_method`.
- Local files: downloads go only into the download folder (subfolders allowed), never
  overwrite an existing file, and never follow symlinks out of the folder. `attach_file`
  reads only from the upload folders and refuses hidden files and folders (such as
  `~/.ssh` or `.env`). This limits what a prompt injection in Odoo data could make the
  model read or write.
- Errors from Odoo reach the model (so it can fix its call), with your password, API key,
  and configured HTTP header values redacted. Unexpected errors return a generic message.
- `register_payment` refuses moves that are not posted or have nothing left to pay.
  (Odoo 18's payment wizard would otherwise create a payment for a cancelled invoice.)

## Example prompts

```
Which customer invoices are overdue? Group them by customer with the open amounts.

Create a draft bill from Hetzner for 49.90 EUR, dated today, on account 6810,
attach ~/Downloads/hetzner-invoice.pdf, and show it to me before posting.

Register a payment for INV/2026/00042 on 2026-11-18 via the Bank journal.

Post a note on BILL/2026/0012: "Checked against the contract."
```
