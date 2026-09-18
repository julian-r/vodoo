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
const enterprise = process.env.ODOO_ENTERPRISE === "1";
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

async function cleanupRecords(
  records: readonly { model: string; id: number | null | undefined }[],
): Promise<void> {
  let firstError: unknown;
  for (const record of records) {
    if (record.id === null || record.id === undefined) continue;
    try {
      await client.unlink(record.model, [record.id]);
    } catch (error) {
      firstError ??= error;
    }
  }
  if (firstError !== undefined) throw firstError;
}

describe.sequential(`Odoo ${majorVersion} TypeScript SDK`, () => {
  beforeAll(async () => {
    await client.getUid();
  });

  afterAll(async () => {
    let cleanupError: unknown;
    try {
      await cleanupRecords([
        { model: "project.milestone", id: milestoneId },
        { model: "project.project", id: projectId },
      ]);
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

  it("covers task, CRM, activity, security, and shared binary APIs", async () => {
    const suffix = `${majorVersion}-${Date.now()}`;
    let taskId: number | undefined;
    let taskTagId: number | undefined;
    let attachmentId: number | undefined;
    let leadId: number | undefined;
    let primaryError: unknown;
    if (projectId === null) throw new Error("project fixture was not created");

    try {
      taskId = await client.tasks.create(
        `TS namespace task ${suffix}`,
        projectId,
        {
          description: "**Worker-safe** task",
        },
      );
      taskTagId = await client.tasks.createTag(`TS tag ${suffix}`, 3);
      await client.tasks.addTag(taskId, taskTagId);
      attachmentId = await client.tasks.attach(
        taskId,
        new Uint8Array([0, 1, 2, 255]),
        `worker-${suffix}.bin`,
      );
      expect([...(await client.tasks.attachmentData(attachmentId))]).toEqual([
        0, 1, 2, 255,
      ]);

      const task = await client.tasks.get(taskId);
      expect(task.name).toBe(`TS namespace task ${suffix}`);
      expect(task.create_date).toBeInstanceOf(Date);

      leadId = await client.crm.create(`TS opportunity ${suffix}`, {
        expectedRevenue: 1234.5,
      });
      const lead = await client.crm.get(leadId);
      expect(lead.name).toBe(`TS opportunity ${suffix}`);
      expect(lead.create_date).toBeInstanceOf(Date);

      const activities = await client.activities.list({
        domain: [["res_model", "=", "project.task"]],
        limit: 2,
      });
      expect(Array.isArray(activities)).toBe(true);

      const user = await client.security.getUser(await client.getUid());
      expect(user.login).toBe(config.username);

      const accountMoveModel = await client.search("ir.model", {
        domain: [["model", "=", "account.move"]],
        limit: 1,
      });
      expect(accountMoveModel).toHaveLength(1);
      expect(Array.isArray(await client.accountMoves.list({ limit: 1 }))).toBe(
        true,
      );
      expect(await client.accountMoves.fields()).toHaveProperty("date");
    } catch (error) {
      primaryError = error;
      throw error;
    } finally {
      try {
        await cleanupRecords([
          { model: "crm.lead", id: leadId },
          { model: "ir.attachment", id: attachmentId },
          { model: "project.tags", id: taskTagId },
          { model: "project.task", id: taskId },
        ]);
      } catch (cleanupError) {
        if (primaryError === undefined) throw cleanupError;
        console.error(
          "cleanup failed after primary test failure",
          cleanupError,
        );
      }
    }
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

  it.skipIf(!enterprise)(
    "covers Enterprise helpdesk, knowledge, documents, and timer namespaces",
    async () => {
      const suffix = `${majorVersion}-${Date.now()}`;
      let ticketId: number | undefined;
      let articleId: number | undefined;
      let folderId: number | undefined;
      let folderModel: "documents.document" | "documents.folder" | undefined;
      let documentId: number | undefined;
      let primaryError: unknown;
      try {
        ticketId = await client.helpdesk.create(`TS ticket ${suffix}`, {
          description: "Created by the TypeScript integration suite",
        });
        expect((await client.helpdesk.get(ticketId)).name).toBe(
          `TS ticket ${suffix}`,
        );

        articleId = await client.knowledge.create(`TS article ${suffix}`, {
          body: "# TypeScript integration",
        });
        expect((await client.knowledge.get(articleId)).name).toBe(
          `TS article ${suffix}`,
        );
        expect(await client.knowledge.resolveUrl(articleId)).toContain(
          String(articleId),
        );

        const typeField = await client.fieldsGet(
          "documents.document",
          ["type"],
          ["selection"],
        );
        const selection =
          typeof typeField.type === "object" && typeField.type !== null
            ? (typeField.type as Record<string, unknown>).selection
            : undefined;
        const modernFolders = Array.isArray(selection)
          ? selection.some(
              (option) => Array.isArray(option) && option[0] === "folder",
            )
          : typeof selection === "object" &&
            selection !== null &&
            Object.hasOwn(selection, "folder");
        folderModel = modernFolders ? "documents.document" : "documents.folder";
        folderId = await client.create(
          folderModel,
          modernFolders
            ? { name: `TS folder ${suffix}`, type: "folder" }
            : { name: `TS folder ${suffix}` },
        );
        documentId = await client.documents.upload(
          new Uint8Array([84, 83]),
          `typescript-${suffix}.txt`,
          { folderId, mimetype: "text/plain" },
        );
        const downloaded = await client.documents.downloadFile(documentId);
        expect([...downloaded.data]).toEqual([84, 83]);

        expect(
          Array.isArray(await client.timer.list({ days: -1, limit: 5 })),
        ).toBe(true);
      } catch (error) {
        primaryError = error;
        throw error;
      } finally {
        try {
          await cleanupRecords([
            { model: "documents.document", id: documentId },
            { model: folderModel ?? "documents.document", id: folderId },
            { model: "knowledge.article", id: articleId },
            { model: "helpdesk.ticket", id: ticketId },
          ]);
        } catch (cleanupError) {
          if (primaryError === undefined) throw cleanupError;
          console.error(
            "cleanup failed after primary test failure",
            cleanupError,
          );
        }
      }
    },
  );
});
