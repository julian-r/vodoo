# Timers

`TimerNamespace` for timer and timesheet management, accessed as `client.timer`.

Legacy running state comes from `timer.timer`. Access and transport failures from
that lookup propagate through list, active, and stop operations; they are not
interpreted as an empty timer list. A successful empty query still returns no
running timers. Optional task/ticket display-label reads remain best-effort.
This behavior is consistent across synchronous/asynchronous Python, TypeScript,
and Swift.

::: vodoo.timer
    options:
      show_source: true
      members_order: source
