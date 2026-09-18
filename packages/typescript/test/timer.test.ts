import { describe, expect, it } from "vitest";

import { RecordingClient } from "../src/testing.js";
import {
  TimerHandle,
  TimerNamespace,
  TimerSource,
  TimerState,
  Timesheet,
  mergeRunningTimers,
  parseTimesheet,
} from "../src/namespaces/timer.js";

describe("timer value types", () => {
  it("uses native dates and calculates elapsed time", () => {
    const timesheet = new Timesheet(
      1,
      "Implement",
      "Project",
      new TimerSource("task", 2, "Task"),
      1.5,
      new Date("2025-01-02T10:00:00.000Z"),
      new Date("2025-01-02T00:00:00.000Z"),
    );

    expect(timesheet.state).toBe(TimerState.Running);
    expect(
      timesheet.elapsedFormatted(new Date("2025-01-02T10:45:00.000Z")),
    ).toBe("2:15");
    expect(timesheet.displayLabel).toBe("🔧 Task");
    expect(timesheet.toObject().date).toBeInstanceOf(Date);
  });

  it("parses wire records and merges running state by source", () => {
    const stopped = parseTimesheet({
      id: 8,
      name: "Work",
      project_id: [3, "Project"],
      task_id: [4, "Task"],
      unit_amount: 2,
      timer_start: false,
      date: "2025-01-02",
    });
    expect(stopped).not.toBeNull();
    const running = new Timesheet(
      -9,
      "",
      "Project",
      new TimerSource("task", 4, "Task"),
      0,
      new Date("2025-01-02T11:00:00.000Z"),
      new Date("2025-01-02T00:00:00.000Z"),
    );

    const merged = mergeRunningTimers([stopped!], [running]);
    expect(merged).toHaveLength(1);
    expect(merged[0]?.id).toBe(8);
    expect(merged[0]?.timerStart).toEqual(new Date("2025-01-02T11:00:00.000Z"));
  });
});

describe("TimerNamespace", () => {
  it("uses analytic-line timer state on JSON-2", async () => {
    const client = new RecordingClient(
      "https://odoo.example.com",
      [
        7,
        [],
        [
          {
            id: 8,
            name: "Work",
            project_id: [3, "Project"],
            task_id: [4, "Task"],
            unit_amount: 0.5,
            timer_start: "2025-01-02 10:00:00",
            date: "2025-01-02",
          },
        ],
      ],
      undefined,
      true,
    );
    const timer = new TimerNamespace(client);

    const result = await timer.list({ days: -1 });
    expect(result).toHaveLength(1);
    expect(result[0]?.state).toBe(TimerState.Running);
    expect(result[0]?.timerStart).toEqual(new Date("2025-01-02T10:00:00.000Z"));
    expect(client.calls).toHaveLength(3);
  });

  it("merges legacy timer.timer records and tolerates missing helpdesk", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      7,
      new Error("Unknown field helpdesk_ticket_id"),
      [],
      [
        {
          id: 50,
          timer_start: "2025-01-02 10:00:00",
          res_model: "project.task",
          res_id: 4,
        },
      ],
      [{ id: 4, display_name: "Task 4", project_id: [3, "Project"] }],
    ]);
    const timer = new TimerNamespace(client);

    const result = await timer.list({ days: -1 });
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual(
      expect.objectContaining({
        id: -50,
        projectName: "Project",
        source: expect.objectContaining({
          kind: "task",
          id: 4,
          name: "Task 4",
        }),
      }),
    );
    expect(client.calls[3]).toEqual({
      method: "searchRead",
      args: [
        "timer.timer",
        {
          domain: [
            ["user_id", "=", 7],
            ["timer_start", "!=", false],
            ["timer_pause", "=", false],
          ],
          fields: ["timer_start", "res_model", "res_id"],
        },
      ],
    });
  });

  it("routes JSON-2 stops through the confirmation wizard", async () => {
    const client = new RecordingClient(
      "https://odoo.example.com",
      [
        new Error("Unknown field helpdesk_ticket_id"),
        [
          {
            id: 12,
            name: "Standalone",
            project_id: false,
            task_id: false,
            unit_amount: 0,
            timer_start: "2025-01-02 10:00:00",
            date: "2025-01-02",
          },
        ],
        {
          type: "ir.actions.act_window",
          res_model: "hr.timesheet.stop.timer.confirmation.wizard",
          context: { default_timesheet_id: 12 },
        },
        91,
        true,
      ],
      undefined,
      true,
    );
    const timer = new TimerNamespace(client);

    await timer.stopTimesheet(12);
    expect(client.calls.slice(2)).toEqual([
      {
        method: "execute",
        args: ["account.analytic.line", "action_timer_stop", [[12]], undefined],
      },
      {
        method: "create",
        args: [
          "hr.timesheet.stop.timer.confirmation.wizard",
          { timesheet_id: 12 },
          undefined,
        ],
      },
      {
        method: "execute",
        args: [
          "hr.timesheet.stop.timer.confirmation.wizard",
          "action_stop_timer",
          [[91]],
          { context: { default_timesheet_id: 12 } },
        ],
      },
    ]);
  });

  it.each([
    {
      kind: "task" as const,
      sourceId: 4,
      model: "project.task.create.timesheet",
      context: { active_id: 4, default_time_spent: 90 },
      values: { task_id: 4, description: "/", time_spent: 90 },
      method: "save_timesheet",
    },
    {
      kind: "ticket" as const,
      sourceId: 5,
      model: "helpdesk.ticket.create.timesheet",
      context: { active_id: 5, default_time_spent: 60 },
      values: { ticket_id: 5, description: "/", time_spent: 60 },
      method: "action_generate_timesheet",
    },
  ])("handles the legacy $kind stop wizard", async (example) => {
    const client = new RecordingClient("https://odoo.example.com", [
      7,
      {
        type: "ir.actions.act_window",
        res_model: example.model,
        context: example.context,
      },
      92,
      true,
    ]);
    const timer = new TimerNamespace(client);
    const timesheet = new Timesheet(
      12,
      "Work",
      "Project",
      new TimerSource(example.kind, example.sourceId, "Source"),
      0,
      new Date("2025-01-02T10:00:00.000Z"),
      new Date("2025-01-02T00:00:00.000Z"),
    );

    await timer.stopOne(timesheet);
    expect(client.calls[2]).toEqual({
      method: "create",
      args: [example.model, example.values, undefined],
    });
    expect(client.calls[3]).toEqual({
      method: "execute",
      args: [
        example.model,
        example.method,
        [[92]],
        { context: example.context },
      ],
    });
  });

  it("finds JSON-2 timers that remained active across midnight", async () => {
    const client = new RecordingClient(
      "https://odoo.example.com",
      [
        7,
        [],
        [
          {
            id: 8,
            name: "Yesterday",
            project_id: [3, "Project"],
            task_id: [4, "Task"],
            unit_amount: 0,
            timer_start: "2025-01-01 23:59:00",
            date: "2025-01-01",
          },
        ],
      ],
      undefined,
      true,
    );

    const active = await new TimerNamespace(client).active();
    expect(active).toHaveLength(1);
    expect(client.calls[2]?.args[1]).toMatchObject({
      domain: [["user_id", "=", 7]],
    });
  });

  it("starts task and ticket timers and stops a task through its handle", async () => {
    const taskClient = new RecordingClient(
      "https://odoo.example.com",
      [
        true,
        7,
        [],
        [
          {
            id: 8,
            name: "Task work",
            project_id: [3, "Project"],
            task_id: [4, "Task"],
            unit_amount: 0,
            timer_start: "2025-01-02 10:00:00",
            date: "2025-01-02",
          },
        ],
        7,
        true,
      ],
      undefined,
      true,
    );
    const timer = new TimerNamespace(taskClient);
    const handle = await timer.startTask(4);
    expect(handle).toBeInstanceOf(TimerHandle);
    await handle.stop();
    expect(taskClient.calls[0]).toEqual({
      method: "execute",
      args: ["project.task", "action_timer_start", [[4]], undefined],
    });
    expect(taskClient.calls.at(-1)).toEqual({
      method: "execute",
      args: ["account.analytic.line", "action_timer_stop", [[8]], undefined],
    });

    const ticketClient = new RecordingClient(undefined, [true]);
    const ticketHandle = await new TimerNamespace(ticketClient).startTicket(5);
    expect(ticketHandle).toBeInstanceOf(TimerHandle);
    expect(ticketClient.calls[0]).toEqual({
      method: "execute",
      args: ["helpdesk.ticket", "action_timer_start", [[5]], undefined],
    });
  });

  it("raises when a task handle has no running timer", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      7,
      new Error("Unknown field helpdesk_ticket_id"),
      [],
      [],
    ]);
    const handle = new TimerHandle(new TimerNamespace(client), "task", 4);
    await expect(handle.stop()).rejects.toThrow(
      "No running timer found for task 4",
    );
  });

  it("targets the source model when starting a legacy task timesheet", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      new Error("Unknown field helpdesk_ticket_id"),
      [
        {
          id: 12,
          name: "Task work",
          project_id: [3, "Project"],
          task_id: [4, "Task"],
          unit_amount: 0,
          timer_start: false,
          date: "2025-01-02",
        },
      ],
      true,
    ]);
    const timer = new TimerNamespace(client);

    await timer.startTimesheet(12);
    expect(client.calls.at(-1)).toEqual({
      method: "execute",
      args: ["project.task", "action_timer_start", [[4]], undefined],
    });
  });
});
