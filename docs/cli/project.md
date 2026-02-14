# vodoo project

Manage Odoo Projects (`project.project`).

## Commands

### list

List projects with optional filters.

```bash
# List all projects
vodoo project list

# Search by name
vodoo project list --search "Website"

# Filter by user
vodoo project list --user "John Doe"

# Filter by stage
vodoo project list --stage "In Progress"
```

**Options:**

| Option | Description |
|--------|-------------|
| `--search` / `-s` | Search by project name |
| `--user` | Filter by responsible user |
| `--stage` | Filter by stage name |
| `--limit` | Maximum records (default: 50) |
| `--simple` | Plain TSV output |

### show

```bash
vodoo project show 5
vodoo project show 5 --html
```

### comment / note

```bash
vodoo project comment 5 "Project update"
vodoo project note 5 "Internal note"
```

### set

```bash
vodoo project set 5 name="Renamed Project"
```

### tags / tag

```bash
vodoo project tags
vodoo project tag 5 3
```

### attachments / attach / download

```bash
vodoo project attachments 5
vodoo project attach 5 roadmap.pdf
vodoo project download 123
```

### url

```bash
vodoo project url 5
```
