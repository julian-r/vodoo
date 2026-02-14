# AI Assistant Integration

Vodoo is designed with an **AI-first** approach — its clear, consistent CLI structure makes it ideal for use with Claude Code, GitHub Copilot, and similar AI coding assistants.

## Why It Works

1. **Consistent command patterns** — every domain uses the same verbs (`list`, `show`, `comment`, `note`, `set`, `tag`, `attach`)
2. **Readable output** — Rich tables and structured data that AI can parse
3. **Natural language mapping** — commands map directly to plain English requests
4. **Simple output mode** — `--simple` flag gives plain TSV for easy programmatic parsing

## Example Workflow with Claude Code

```
You: "Show me all tickets assigned to me that are in progress"
Claude: [runs: vodoo helpdesk list --assigned-to "Your Name" --stage "In Progress"]

You: "Add an internal note to ticket 123 saying we're waiting for customer response"
Claude: [runs: vodoo helpdesk note 123 "Waiting for customer response"]

You: "Download all attachments from ticket 456"
Claude: [runs: vodoo helpdesk attachments 456, then downloads each]

You: "What CRM opportunities are in the Proposition stage?"
Claude: [runs: vodoo crm list --type opportunity --stage "Proposition"]

You: "Start a timer on task 42 and update its priority to high"
Claude: [runs: vodoo timer start 42]
Claude: [runs: vodoo project-task set 42 priority=2]
```

## Setting Up for AI Assistants

### 1. Configure Vodoo

Ensure your credentials are set up in `~/.config/vodoo/config.env` so the AI assistant can run commands without prompting for credentials.

### 2. Add to your project context

Add a note to your project's `CLAUDE.md` or equivalent AI context file:

```markdown
## Odoo Integration

This project uses Vodoo (`vodoo`) CLI for Odoo operations.
Available commands: helpdesk, project-task, project, crm, knowledge, timer, model, security.
Run `vodoo <command> --help` for options.
```

### 3. Use natural language

The AI assistant will translate your requests into the appropriate `vodoo` commands. No need to memorize syntax.

## Tips

- Use `--simple` when you want the AI to parse output programmatically
- The `model` subcommand lets the AI work with *any* Odoo model, not just the built-in ones
- Chain commands: "List tickets, then add a note to each one mentioning the weekly review"
