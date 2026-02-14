# vodoo timer

Manage timers and timesheets.

## Commands

### status

Show today's timesheets with running state.

```bash
vodoo timer status
```

### active

Show only currently running timers.

```bash
vodoo timer active
```

### start

Start a timer on a task or ticket, or resume a stopped timesheet.

```bash
# Start on a project task
vodoo timer start --task 42

# Start on a helpdesk ticket (enterprise)
vodoo timer start --ticket 99

# Resume a stopped timesheet
vodoo timer start --timesheet 15
```

**Options:**

| Option | Description |
|--------|-------------|
| `--task` | Project task ID to start timer on |
| `--ticket` | Helpdesk ticket ID to start timer on |
| `--timesheet` | Existing timesheet ID to resume |

!!! note
    You must provide exactly one of `--task`, `--ticket`, or `--timesheet`.

### stop

Stop running timers.

```bash
# Stop all running timers
vodoo timer stop

# Stop a specific timesheet timer
vodoo timer stop --timesheet 15
```
