# vodoo project-task

Manage Odoo Project Tasks.

## Commands

### list

List project tasks with optional filters.

```bash
# List all tasks
vodoo project-task list

# Filter by project
vodoo project-task list --project "Website Redesign"

# Filter by stage
vodoo project-task list --stage "In Progress"

# Filter by assigned user
vodoo project-task list --assigned-to "Jane"

# Search across text fields
vodoo project-task list --search "login bug"

# Combine filters
vodoo project-task list --project "Mobile App" --stage "Done" --limit 20
```

**Options:**

| Option | Description |
|--------|-------------|
| `--project` | Filter by project name (partial match) |
| `--stage` | Filter by stage name |
| `--assigned-to` | Filter by assigned user name |
| `--search` / `-s` | Search across text fields |
| `--limit` | Maximum records (default: 50) |
| `--simple` | Plain TSV output |

### show

```bash
vodoo project-task show 42
vodoo project-task show 42 --html
```

### comment / note

```bash
vodoo project-task comment 42 "Public update"
vodoo project-task note 42 "Internal note for team"
```

### set

```bash
vodoo project-task set 42 priority=1 name="Renamed task"
```

### tags / tag

```bash
vodoo project-task tags
vodoo project-task tag 42 7
```

### attachments / attach / download

```bash
vodoo project-task attachments 42
vodoo project-task attach 42 spec.pdf
vodoo project-task download 789
```

### url

```bash
vodoo project-task url 42
```
