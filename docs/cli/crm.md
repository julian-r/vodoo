# vodoo crm

Manage Odoo CRM leads and opportunities.

## Commands

### list

List CRM leads and opportunities.

```bash
# List all
vodoo crm list

# Search across name, email, phone, contact, description
vodoo crm list --search "acme"
vodoo crm list -s "john@example.com"

# Filter by type
vodoo crm list --type lead
vodoo crm list --type opportunity

# Filter by stage, team, user, or partner
vodoo crm list --stage "Qualified"
vodoo crm list --team "Direct Sales"
vodoo crm list --user "John Doe"
vodoo crm list --partner "Acme Corp"

# Combine filters
vodoo crm list --search "software" --type opportunity --stage "Proposition"
```

**Options:**

| Option | Description |
|--------|-------------|
| `--search` / `-s` | Search across text fields |
| `--type` | Filter: `lead` or `opportunity` |
| `--stage` | Filter by stage name |
| `--team` | Filter by sales team |
| `--user` | Filter by salesperson |
| `--partner` | Filter by partner/company |
| `--limit` | Maximum records (default: 50) |
| `--simple` | Plain TSV output |

### show

```bash
vodoo crm show 123
```

### comment / note

```bash
# Add public comment
vodoo crm comment 123 "Sent proposal via email"

# Add internal note
vodoo crm note 123 "Followed up via phone"
```

### set

```bash
vodoo crm set 123 expected_revenue=50000 probability=75
```

### tags / tag

```bash
vodoo crm tags
vodoo crm tag 123 4
```

### attachments / attach / download

```bash
vodoo crm attachments 123
vodoo crm attach 123 proposal.pdf
vodoo crm download 456
```

### url

```bash
vodoo crm url 123
```
