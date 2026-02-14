# CLI Reference

Vodoo provides a Typer-based CLI with the following subcommands:

| Command | Description |
|---------|-------------|
| [`helpdesk`](helpdesk.md) | Helpdesk ticket operations (enterprise) |
| [`project-task`](project-task.md) | Project task operations |
| [`project`](project.md) | Project operations |
| [`crm`](crm.md) | CRM lead/opportunity operations |
| [`knowledge`](knowledge.md) | Knowledge article operations (enterprise) |
| [`timer`](timer.md) | Timer and timesheet management |
| [`model`](model.md) | Generic CRUD operations for any Odoo model |
| [`security`](security.md) | Security group and user management |

## Global Options

```
vodoo --help
vodoo <command> --help
```

## Output Modes

By default, Vodoo uses Rich tables for colorful terminal output. Use `--simple` on list commands for plain TSV output suitable for piping:

```bash
vodoo helpdesk list --simple | cut -f1,2
```

## Common Patterns

All domain subcommands (`helpdesk`, `project-task`, `project`, `crm`) share a consistent interface:

| Action | Command |
|--------|---------|
| List records | `vodoo <cmd> list [--stage ...] [--search ...] [--limit N]` |
| Show details | `vodoo <cmd> show <ID>` |
| Add comment | `vodoo <cmd> comment <ID> "message"` |
| Add note | `vodoo <cmd> note <ID> "message"` |
| Update fields | `vodoo <cmd> set <ID> field=value ...` |
| List tags | `vodoo <cmd> tags` |
| Add tag | `vodoo <cmd> tag <ID> <TAG_ID>` |
| Attachments | `vodoo <cmd> attachments <ID>` |
| Upload file | `vodoo <cmd> attach <ID> <FILE>` |
| Download | `vodoo <cmd> download <ATTACHMENT_ID>` |
| Get URL | `vodoo <cmd> url <ID>` |
