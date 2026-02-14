# vodoo knowledge

Manage Odoo Knowledge articles (requires Odoo Enterprise).

## Commands

### list

List knowledge articles.

```bash
# List all articles
vodoo knowledge list

# Filter by category
vodoo knowledge list --category workspace

# List favorites only
vodoo knowledge list --favorite

# Search by name
vodoo knowledge list --name "Getting Started"
```

**Options:**

| Option | Description |
|--------|-------------|
| `--category` | Filter by category (e.g., `workspace`) |
| `--favorite` | Show only favorite articles |
| `--name` | Filter by article name |
| `--limit` | Maximum records (default: 50) |
| `--simple` | Plain TSV output |

### show

Show article details including content.

```bash
vodoo knowledge show 123

# Show raw HTML content
vodoo knowledge show 123 --html
```

### note

Add an internal note to an article.

```bash
vodoo knowledge note 123 "Updated the installation section"
```

### url

```bash
vodoo knowledge url 123
```

!!! note "Limitations"
    - ✅ Read/write existing articles
    - ✅ Create child articles (under existing parent)
    - ❌ Create root workspace articles (requires internal user)
    - ❌ Delete articles (requires Administrator)
