import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { OdooClient } from "../../src/client.js";
import type { OdooConfig } from "../../src/types.js";

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === "") {
    throw new Error(
      `${name} is required for TypeScript Odoo integration tests`,
    );
  }
  return value;
}

const majorVersion = Number(requiredEnvironment("ODOO_MAJOR_VERSION"));
const config: OdooConfig = {
  url: requiredEnvironment("ODOO_URL"),
  database: requiredEnvironment("ODOO_DATABASE"),
  username: requiredEnvironment("ODOO_USERNAME"),
  password: requiredEnvironment("ODOO_PASSWORD"),
};

const client = new OdooClient(config);
const uniqueName = `Vodoo TypeScript Integration ${majorVersion} ${Date.now()}`;
let projectId: number | null = null;
let milestoneId: number | null = null;

describe.sequential(`Odoo ${majorVersion} TypeScript SDK`, () => {
  beforeAll(async () => {
    await client.getUid();
  });

  afterAll(async () => {
    let cleanupError: unknown;
    try {
      if (milestoneId !== null) {
        await client.unlink("project.milestone", [milestoneId]);
      }
      if (projectId !== null) {
        await client.unlink("project.project", [projectId]);
      }
    } catch (error) {
      cleanupError = error;
    } finally {
      await client.close();
    }
    if (cleanupError !== undefined) throw cleanupError;
  });

  it("auto-detects the expected transport and authenticates", async () => {
    await expect(client.getUid()).resolves.toBeGreaterThan(0);
    expect(client.isJson2).toBe(majorVersion >= 19);
  });

  it("runs generic CRUD through the selected transport", async () => {
    projectId = await client.create("project.project", {
      name: uniqueName,
      date_start: "2026-04-30",
    });
    expect(projectId).toBeGreaterThan(0);

    await expect(
      client.write("project.project", [projectId], { color: 3 }),
    ).resolves.toBe(true);

    const rows = await client.searchRead("project.project", {
      domain: [["id", "=", projectId]],
      fields: ["id", "name", "color"],
      limit: 1,
    });
    expect(rows).toHaveLength(1);
    expect(rows[0]?.name).toBe(uniqueName);
    expect(rows[0]?.color).toBe(3);
  });

  it("exercises the generated project namespace", async () => {
    if (projectId === null) throw new Error("project fixture was not created");

    const listed = await client.projects.list({
      domain: [["id", "=", projectId]],
    });
    expect(listed).toHaveLength(1);
    expect(listed[0]?.name).toBe(uniqueName);
    expect(listed[0]?.date_start).toEqual(new Date("2026-04-30T00:00:00.000Z"));

    const project = await client.projects.get(projectId);
    expect(project.id).toBe(projectId);
    expect(project.name).toBe(uniqueName);

    await expect(client.projects.set(projectId, { color: 4 })).resolves.toBe(
      true,
    );
    const fields = await client.projects.fields();
    expect(fields).toHaveProperty("name");
    await expect(client.projects.resolveProjectId(uniqueName)).resolves.toBe(
      projectId,
    );
    await expect(client.projects.stages(projectId)).resolves.toBeInstanceOf(
      Array,
    );
    expect(client.projects.url(projectId)).toContain(
      `id=${projectId}&model=project.project`,
    );
  });

  it("runs the project milestone workflow available in Community", async () => {
    if (projectId === null) throw new Error("project fixture was not created");

    const milestoneModels = await client.search("ir.model", {
      domain: [["model", "=", "project.milestone"]],
      limit: 1,
    });
    expect(milestoneModels).toHaveLength(1);

    milestoneId = await client.projects.createMilestone(
      projectId,
      "TypeScript milestone",
      new Date("2026-05-31T00:00:00.000Z"),
    );
    expect(milestoneId).toBeGreaterThan(0);

    const milestones = await client.projects.milestones(projectId);
    const milestone = milestones.find(
      (candidate) => candidate.id === milestoneId,
    );
    expect(milestone?.deadline).toEqual(new Date("2026-05-31T00:00:00.000Z"));

    await expect(client.projects.reachMilestone(milestoneId)).resolves.toBe(
      true,
    );
    await expect(client.projects.milestoneTasks(milestoneId)).resolves.toEqual(
      [],
    );
  });
});
