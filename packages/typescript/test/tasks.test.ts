import { describe, expect, it } from "vitest";

import { RecordOperationError } from "../src/errors.js";
import { TaskNamespace } from "../src/namespaces/tasks.js";
import { RecordingClient } from "../src/testing.js";

describe("TaskNamespace", () => {
  it("creates tasks with Markdown, x2many values, and project context", async () => {
    const client = new RecordingClient(undefined, [21]);
    await expect(
      new TaskNamespace(client).create("Deploy", 7, {
        description: "**Ship it**",
        userIds: [2],
        tagIds: [3],
        parentId: 4,
        extraFields: {
          name: "Ignored",
          project_id: 999,
          description: "Ignored",
          priority: "1",
        },
      }),
    ).resolves.toBe(21);
    expect(client.calls[0]).toEqual({
      method: "create",
      args: [
        "project.task",
        {
          name: "Deploy",
          project_id: 7,
          priority: "1",
          description: "<p><strong>Ship it</strong></p>",
          user_ids: [[6, 0, [2]]],
          tag_ids: [[6, 0, [3]]],
          parent_id: 4,
        },
        { default_project_id: 7 },
      ],
    });
  });

  it("validates milestone project membership before writing", async () => {
    const client = new RecordingClient(undefined, [
      [{ project_id: [7, "Project"] }],
      [{ project_id: [7, "Project"] }],
      true,
    ]);
    await expect(new TaskNamespace(client).setMilestone(2, 9)).resolves.toBe(
      true,
    );
    expect(client.calls[2]).toEqual({
      method: "write",
      args: ["project.task", [2], { milestone_id: 9 }],
    });
  });

  it("rejects milestones from another project", async () => {
    const namespace = new TaskNamespace(
      new RecordingClient(undefined, [
        [{ project_id: [7, "A"] }],
        [{ project_id: [8, "B"] }],
      ]),
    );
    await expect(namespace.setMilestone(2, 9)).rejects.toBeInstanceOf(
      RecordOperationError,
    );
  });

  it("manages dependencies, native UTC schedules, and tags", async () => {
    const client = new RecordingClient(undefined, [true, true, true, 88, true]);
    const tasks = new TaskNamespace(client);
    await expect(tasks.addDependencies(2, [3, 4])).resolves.toBe(true);
    await expect(tasks.clearDependencies(2)).resolves.toBe(true);
    await expect(
      tasks.schedule(
        2,
        new Date("2026-04-05T06:07:08Z"),
        new Date("2026-05-06T23:59:00Z"),
      ),
    ).resolves.toBe(true);
    await expect(tasks.createTag("Backend", 0)).resolves.toBe(88);
    await expect(tasks.deleteTag(88)).resolves.toBe(true);
    expect(client.calls).toEqual([
      {
        method: "write",
        args: [
          "project.task",
          [2],
          {
            depend_on_ids: [
              [4, 3, 0],
              [4, 4, 0],
            ],
          },
        ],
      },
      {
        method: "write",
        args: ["project.task", [2], { depend_on_ids: [[5, 0, 0]] }],
      },
      {
        method: "write",
        args: [
          "project.task",
          [2],
          {
            planned_date_begin: "2026-04-05 06:07:08",
            date_deadline: "2026-05-06",
          },
        ],
      },
      {
        method: "create",
        args: ["project.tags", { name: "Backend", color: 0 }, undefined],
      },
      { method: "unlink", args: ["project.tags", [88]] },
    ]);
  });
});
