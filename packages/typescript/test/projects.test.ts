import { describe, expect, it } from "vitest";

import { RecordNotFoundError, VodooError } from "../src/errors.js";
import {
  PROJECT_DEFAULT_DETAIL_FIELDS,
  PROJECT_DEFAULT_FIELDS,
  PROJECT_MILESTONE_TASKS,
  PROJECT_MILESTONES,
  PROJECT_STAGES,
} from "../src/generated/projects.js";
import { ProjectNamespace } from "../src/namespaces/projects.js";
import { RecordingClient } from "../src/testing.js";

describe("ProjectNamespace common slice", () => {
  it("lists with generated defaults and decodes native dates", async () => {
    const client = new RecordingClient("https://odoo.example.com/", [
      [{ id: 7, name: "Website", date_start: "2026-01-02", date: false }],
    ]);
    const projects = new ProjectNamespace(client);

    const result = await projects.list();

    expect(result[0]?.date_start).toEqual(new Date("2026-01-02T00:00:00Z"));
    expect(client.calls).toEqual([
      {
        method: "searchRead",
        args: [
          "project.project",
          {
            fields: PROJECT_DEFAULT_FIELDS,
            limit: 50,
            order: "create_date desc",
          },
        ],
      },
    ]);
  });

  it("gets, sets, lists fields, builds URL, and reports missing records", async () => {
    const client = new RecordingClient("https://odoo.example.com/", [
      [{ id: 7, name: "Website", write_date: "2026-01-02 03:04:05" }],
      true,
      { name: { type: "char" } },
      [],
    ]);
    const projects = new ProjectNamespace(client);

    const project = await projects.get(7);
    expect(project.write_date).toEqual(new Date("2026-01-02T03:04:05Z"));
    await expect(projects.set(7, { color: 3 })).resolves.toBe(true);
    await expect(projects.fields()).resolves.toEqual({
      name: { type: "char" },
    });
    expect(projects.url(7)).toBe(
      "https://odoo.example.com/web#id=7&model=project.project&view_type=form",
    );
    await expect(projects.get(999)).rejects.toBeInstanceOf(RecordNotFoundError);

    expect(client.calls[0]).toEqual({
      method: "read",
      args: ["project.project", [7], PROJECT_DEFAULT_DETAIL_FIELDS],
    });
    expect(client.calls[1]).toEqual({
      method: "write",
      args: ["project.project", [7], { color: 3 }],
    });
    expect(client.calls[2]).toEqual({
      method: "fieldsGet",
      args: ["project.project", undefined, undefined],
    });
  });
});

describe("ProjectNamespace project operations", () => {
  it("lists all stages or filters by project", async () => {
    const client = new RecordingClient(undefined, [[], []]);
    const projects = new ProjectNamespace(client);
    await projects.stages();
    await projects.stages(7);
    expect(client.calls).toEqual([
      {
        method: "searchRead",
        args: [
          "project.task.type",
          { domain: [], fields: PROJECT_STAGES, order: "sequence" },
        ],
      },
      {
        method: "searchRead",
        args: [
          "project.task.type",
          {
            domain: [["project_ids", "in", [7]]],
            fields: PROJECT_STAGES,
            order: "sequence",
          },
        ],
      },
    ]);
  });

  it("resolves numeric IDs without a lookup", async () => {
    const client = new RecordingClient(undefined, []);
    const projects = new ProjectNamespace(client);
    await expect(projects.resolveProjectId(7)).resolves.toBe(7);
    await expect(projects.resolveProjectId("7")).resolves.toBe(7);
    expect(client.calls).toEqual([]);
  });

  it("resolves an exact case-insensitive project name after =ilike lookup", async () => {
    const client = new RecordingClient(undefined, [
      [
        { id: 1, name: "100XX" },
        { id: 2, name: "100_% Complete" },
      ],
    ]);
    const projects = new ProjectNamespace(client);
    await expect(projects.resolveProjectId("100_% COMPLETE")).resolves.toBe(2);
    expect(client.calls[0]).toEqual({
      method: "searchRead",
      args: [
        "project.project",
        {
          domain: [["name", "=ilike", "100_% COMPLETE"]],
          fields: ["id", "name"],
          order: "id",
        },
      ],
    });
  });

  it.each([
    [[]],
    [
      [
        { id: 1, name: "Website" },
        { id: 2, name: "WEBSITE" },
      ],
    ],
  ] as const)("rejects absent and ambiguous names", async (matches) => {
    const client = new RecordingClient(undefined, [matches]);
    const projects = new ProjectNamespace(client);
    await expect(projects.resolveProjectId("Website")).rejects.toBeInstanceOf(
      VodooError,
    );
  });

  it("lists milestones with native dates", async () => {
    const client = new RecordingClient(undefined, [
      [{ id: 3, name: "Beta", deadline: "2026-04-30", reached_date: false }],
    ]);
    const projects = new ProjectNamespace(client);
    const result = await projects.milestones(7);
    expect(result[0]?.deadline).toEqual(new Date("2026-04-30T00:00:00Z"));
    expect(client.calls[0]).toEqual({
      method: "searchRead",
      args: [
        "project.milestone",
        {
          domain: [["project_id", "=", 7]],
          fields: PROJECT_MILESTONES,
          order: "deadline, id",
        },
      ],
    });
  });

  it("creates a milestone from a strict native UTC date", async () => {
    const client = new RecordingClient(undefined, [91]);
    const projects = new ProjectNamespace(client);
    await expect(
      projects.createMilestone(7, "Beta", new Date("2026-04-30T23:00:00Z")),
    ).resolves.toBe(91);
    expect(client.calls[0]).toEqual({
      method: "create",
      args: [
        "project.milestone",
        { project_id: 7, name: "Beta", deadline: "2026-04-30" },
        undefined,
      ],
    });
  });

  it("reaches milestones and lists their tasks", async () => {
    const client = new RecordingClient(undefined, [
      true,
      [{ id: 5, name: "Task" }],
    ]);
    const projects = new ProjectNamespace(client);
    await expect(projects.reachMilestone(91)).resolves.toBe(true);
    await expect(projects.milestoneTasks(91)).resolves.toEqual([
      { id: 5, name: "Task" },
    ]);
    expect(client.calls).toEqual([
      {
        method: "write",
        args: ["project.milestone", [91], { is_reached: true }],
      },
      {
        method: "searchRead",
        args: [
          "project.task",
          {
            domain: [["milestone_id", "=", 91]],
            fields: PROJECT_MILESTONE_TASKS,
            order: "id",
          },
        ],
      },
    ]);
  });
});
