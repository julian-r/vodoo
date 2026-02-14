# vodoo helpdesk

Manage Odoo Helpdesk tickets (requires Odoo Enterprise).

## Commands

### list

List helpdesk tickets with optional filters.

```bash
# List all tickets (default limit: 50)
vodoo helpdesk list

# Filter by stage
vodoo helpdesk list --stage "In Progress"

# Filter by partner
vodoo helpdesk list --partner "Acme Corp"

# Filter by assigned user
vodoo helpdesk list --assigned-to "John Doe"

# Set custom limit
vodoo helpdesk list --limit 100
```

**Options:**

| Option | Description |
|--------|-------------|
| `--stage` | Filter by stage name (partial match) |
| `--partner` | Filter by partner/customer name |
| `--assigned-to` | Filter by assigned user name |
| `--search` / `-s` | Search across text fields |
| `--limit` | Maximum records (default: 50) |
| `--simple` | Plain TSV output |

### show

Show detailed information for a ticket.

```bash
vodoo helpdesk show 123

# Show raw HTML description
vodoo helpdesk show 123 --html
```

### comment

Add a public comment (visible to customers).

```bash
vodoo helpdesk comment 123 "This is visible to the customer"

# Post as a specific user
vodoo helpdesk comment 123 "Admin reply" --user-id 42
```

### note

Add an internal note (not visible to customers).

```bash
vodoo helpdesk note 123 "Internal team discussion"
```

### set

Update ticket fields.

```bash
vodoo helpdesk set 123 priority=2 name="Updated title"
```

### tags

List all available helpdesk tags.

```bash
vodoo helpdesk tags
```

### tag

Add a tag to a ticket.

```bash
vodoo helpdesk tag 123 5  # Add tag ID 5 to ticket 123
```

### attachments

List attachments for a ticket.

```bash
vodoo helpdesk attachments 123
```

### attach

Upload a file as an attachment.

```bash
vodoo helpdesk attach 123 screenshot.png
```

### download

Download an attachment by ID.

```bash
vodoo helpdesk download 456

# Download to specific path
vodoo helpdesk download 456 --output /path/to/file.pdf

# Download to specific directory
vodoo helpdesk download 456 --output /path/to/directory/
```

### url

Get the web URL for a ticket.

```bash
vodoo helpdesk url 123
```
