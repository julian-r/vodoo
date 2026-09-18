import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { OdooClient } from "../../src/client.js";
import {
  OdooMissingError,
  RecordNotFoundError,
  VodooError,
  computeHealthFlags,
} from "../../src/index.js";
import type { TimerHandle } from "../../src/namespaces/timer.js";
import type { OdooConfig, OdooRecord } from "../../src/types.js";

function requiredEnvironment(name: string): string {
  const value = process.env[name];
  if (value === undefined || value === "") {
    throw new Error(
      `${name} is required for TypeScript Odoo integration tests`,
    );
  }
  return value;
}

function requiredId(value: number | null, fixture: string): number {
  if (value === null) throw new Error(`${fixture} fixture was not created`);
  return value;
}

function relationId(value: unknown): number | null {
  if (typeof value === "number") return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
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
const suffix = `${majorVersion}-${Date.now()}`;
const attachmentIds = new Set<number>();
let uid = 0;
let projectId: number | null = null;
let taskId: number | null = null;
let subtaskId: number | null = null;
let taskTagId: number | null = null;
let milestoneId: number | null = null;
let leadId: number | null = null;
let crmTagId: number | null = null;
let accountMoveId: number | null = null;
let securityUserId: number | null = null;
let ticketId: number | null = null;
let helpdeskTagId: number | null = null;
let articleId: number | null = null;
let folderId: number | null = null;
let folderModel: "documents.document" | "documents.folder" | null = null;
let documentId: number | null = null;
let timerProjectId: number | null = null;
let timerTaskId: number | null = null;
let timerHandle: TimerHandle | null = null;
const timerTimesheetIds = new Set<number>();

async function cleanupRecords(
  records: readonly { model: string; id: number | null | undefined }[],
): Promise<void> {
  let firstError: unknown;
  for (const record of records) {
    if (record.id === null || record.id === undefined) continue;
    try {
      await client.unlink(record.model, [record.id]);
    } catch (error) {
      if (!(error instanceof OdooMissingError)) firstError ??= error;
    }
  }
  if (firstError !== undefined) throw firstError;
}

async function createAccountMove(): Promise<number> {
  const journals = await client.searchRead("account.journal", {
    domain: [["type", "=", "general"]],
    fields: ["id", "default_account_id"],
    limit: 1,
  });
  const journal = journals[0];
  if (journal === undefined)
    throw new Error("No general account journal is available");

  const accounts = await client.searchRead("account.account", {
    fields: ["id"],
    limit: 50,
  });
  const candidateIds = new Set<number>();
  const defaultAccountId = relationId(journal.default_account_id);
  if (defaultAccountId !== null) candidateIds.add(defaultAccountId);
  for (const account of accounts) candidateIds.add(Number(account.id));

  let lastError: unknown;
  for (const accountId of candidateIds) {
    try {
      return await client.create("account.move", {
        move_type: "entry",
        journal_id: journal.id,
        line_ids: [
          [0, 0, { name: "Vodoo TS debit", account_id: accountId, debit: 1 }],
          [0, 0, { name: "Vodoo TS credit", account_id: accountId, credit: 1 }],
        ],
      });
    } catch (error) {
      lastError = error;
    }
  }
  throw (
    lastError ??
    new Error("No account is available for an account-move fixture")
  );
}

async function createAttachment(
  model: "project.task" | "crm.lead" | "helpdesk.ticket" | "knowledge.article",
  recordId: number,
  bytes: readonly number[],
  name: string,
): Promise<number> {
  const namespace = {
    "project.task": client.tasks,
    "crm.lead": client.crm,
    "helpdesk.ticket": client.helpdesk,
    "knowledge.article": client.knowledge,
  }[model];
  const attachmentId = await namespace.attach(
    recordId,
    new Uint8Array(bytes),
    name,
    { mimetype: "application/octet-stream" },
  );
  attachmentIds.add(attachmentId);
  return attachmentId;
}

function expectRecordNamed(
  records: readonly OdooRecord[],
  id: number,
  name: string,
): void {
  const record = records.find((candidate) => candidate.id === id);
  expect(record?.name).toBe(name);
}

describe.sequential(`Odoo ${majorVersion} TypeScript SDK integration`, () => {
  beforeAll(async () => {
    uid = await client.getUid();
  });

  afterAll(async () => {
    let cleanupError: unknown;
    try {
      if (enterprise && timerTaskId !== null) {
        try {
          const active = await client.timer.active();
          for (const timesheet of active) {
            if (
              timesheet.source.kind === "task" &&
              timesheet.source.id === timerTaskId
            ) {
              await client.timer.stopOne(timesheet);
            }
          }
        } catch {
          // Continue deleting fixtures even if Odoo already stopped the timer.
        }
      }
      if (timerTaskId !== null) {
        const discoveredTimesheetIds = await client.search(
          "account.analytic.line",
          {
            domain: [["task_id", "=", timerTaskId]],
          },
        );
        for (const id of discoveredTimesheetIds) timerTimesheetIds.add(id);
      }
      await cleanupRecords([
        ...[...attachmentIds].map((id) => ({ model: "ir.attachment", id })),
        ...[...timerTimesheetIds].map((id) => ({
          model: "account.analytic.line",
          id,
        })),
        { model: "account.move", id: accountMoveId },
        { model: "res.users", id: securityUserId },
        { model: "documents.document", id: documentId },
        { model: folderModel ?? "documents.document", id: folderId },
        { model: "knowledge.article", id: articleId },
        { model: "helpdesk.ticket", id: ticketId },
        { model: "project.task", id: timerTaskId },
        { model: "project.project", id: timerProjectId },
        { model: "helpdesk.tag", id: helpdeskTagId },
        { model: "crm.lead", id: leadId },
        { model: "crm.tag", id: crmTagId },
        { model: "project.task", id: subtaskId },
        { model: "project.task", id: taskId },
        { model: "project.tags", id: taskTagId },
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

  it("connection: authenticates", () => {
    expect(uid).toBeGreaterThan(0);
  });

  it("connection: selects the transport for the Odoo major version", () => {
    expect(client.isJson2).toBe(majorVersion >= 19);
  });

  it("connection: exposes the configured base URL without a trailing slash", () => {
    expect(client.url).toBe(config.url.replace(/\/+$/u, ""));
  });

  it("generic: creates, reads, updates, and deletes a partner", async () => {
    const partnerId = await client.generic.create("res.partner", {
      name: `TS partner ${suffix}`,
    });
    try {
      expect(partnerId).toBeGreaterThan(0);
      await expect(
        client.generic.update("res.partner", partnerId, { comment: "updated" }),
      ).resolves.toBe(true);
      const rows = await client.generic.search("res.partner", {
        domain: [["id", "=", partnerId]],
        fields: ["id", "name", "comment"],
        limit: 1,
      });
      expectRecordNamed(rows, partnerId, `TS partner ${suffix}`);
      expect(rows[0]?.comment).toContain("updated");
    } finally {
      await expect(
        client.generic.delete("res.partner", partnerId),
      ).resolves.toBe(true);
    }
  });

  it("generic: searches with a limit and deterministic order", async () => {
    const rows = await client.generic.search("res.partner", {
      fields: ["id", "name"],
      limit: 2,
      order: "id",
    });
    expect(rows.length).toBeLessThanOrEqual(2);
    if (rows.length === 2)
      expect(Number(rows[0]?.id)).toBeLessThan(Number(rows[1]?.id));
  });

  it("generic: gets field metadata", async () => {
    const fields = await client.fieldsGet(
      "res.partner",
      ["name"],
      ["type", "string"],
    );
    expect(fields).toHaveProperty("name");
  });

  it("generic: performs name_search", async () => {
    const results = await client.nameSearch(
      "res.users",
      config.username,
      [],
      5,
    );
    expect(results.some(([id]) => id === uid)).toBe(true);
  });

  it("generic: calls an arbitrary model method", async () => {
    const result = await client.generic.call("res.partner", "name_search", [], {
      name: "Administrator",
      args: [],
      limit: 5,
    });
    expect(Array.isArray(result)).toBe(true);
  });

  it("projects: creates a project fixture", async () => {
    projectId = await client.create("project.project", {
      name: `TS project ${suffix}`,
      date_start: "2026-04-30",
    });
    expect(projectId).toBeGreaterThan(0);
  });

  it("projects: lists and decodes project dates", async () => {
    const id = requiredId(projectId, "project");
    const rows = await client.projects.list({ domain: [["id", "=", id]] });
    expectRecordNamed(rows, id, `TS project ${suffix}`);
    expect(rows[0]?.date_start).toEqual(new Date("2026-04-30T00:00:00.000Z"));
  });

  it("projects: gets a project", async () => {
    const project = await client.projects.get(requiredId(projectId, "project"));
    expect(project.name).toBe(`TS project ${suffix}`);
  });

  it("projects: updates project fields", async () => {
    const id = requiredId(projectId, "project");
    await expect(client.projects.set(id, { color: 4 })).resolves.toBe(true);
    expect((await client.projects.get(id)).color).toBe(4);
  });

  it("projects: gets project field metadata", async () => {
    await expect(client.projects.fields()).resolves.toHaveProperty("name");
  });

  it("projects: resolves a numeric project ID", async () => {
    const id = requiredId(projectId, "project");
    await expect(client.projects.resolveProjectId(String(id))).resolves.toBe(
      id,
    );
  });

  it("projects: resolves an exact project name", async () => {
    await expect(
      client.projects.resolveProjectId(`TS project ${suffix}`),
    ).resolves.toBe(requiredId(projectId, "project"));
  });

  it("projects: lists project stages", async () => {
    const stages = await client.projects.stages(
      requiredId(projectId, "project"),
    );
    expect(Array.isArray(stages)).toBe(true);
  });

  it("projects: builds a project URL", () => {
    const id = requiredId(projectId, "project");
    expect(client.projects.url(id)).toContain(`id=${id}&model=project.project`);
  });

  it("projects: posts and lists a comment", async () => {
    const id = requiredId(projectId, "project");
    const message = `TS project comment ${suffix}`;
    await expect(
      client.projects.comment(id, message, { userId: uid }),
    ).resolves.toBe(true);
    const messages = await client.projects.messages(id);
    expect(
      messages.some((record) => String(record.body).includes(message)),
    ).toBe(true);
    expect(
      messages.find((record) => String(record.body).includes(message))?.date,
    ).toBeInstanceOf(Date);
  });

  it("projects: posts an internal note", async () => {
    const id = requiredId(projectId, "project");
    await expect(
      client.projects.note(id, `TS project note ${suffix}`, { userId: uid }),
    ).resolves.toBe(true);
  });

  it("projects: round-trips an attachment", async () => {
    const id = requiredId(projectId, "project");
    const attachmentId = await client.projects.attach(
      id,
      new Uint8Array([80, 82, 74]),
      `project-${suffix}.bin`,
    );
    attachmentIds.add(attachmentId);
    expect([...(await client.projects.attachmentData(attachmentId))]).toEqual([
      80, 82, 74,
    ]);
  });

  it("projects: creates a milestone", async () => {
    milestoneId = await client.projects.createMilestone(
      requiredId(projectId, "project"),
      `TS milestone ${suffix}`,
      new Date("2026-05-31T00:00:00.000Z"),
    );
    expect(milestoneId).toBeGreaterThan(0);
  });

  it("projects: lists and decodes milestones", async () => {
    const milestones = await client.projects.milestones(
      requiredId(projectId, "project"),
    );
    const milestone = milestones.find(
      (candidate) => candidate.id === milestoneId,
    );
    expect(milestone?.deadline).toEqual(new Date("2026-05-31T00:00:00.000Z"));
  });

  it("tasks: creates a task with rich text", async () => {
    taskId = await client.tasks.create(
      `TS task ${suffix}`,
      requiredId(projectId, "project"),
      {
        description: "**Worker-safe** task",
      },
    );
    expect(taskId).toBeGreaterThan(0);
  });

  it("tasks: lists tasks", async () => {
    const id = requiredId(taskId, "task");
    expectRecordNamed(
      await client.tasks.list({ domain: [["id", "=", id]] }),
      id,
      `TS task ${suffix}`,
    );
  });

  it("tasks: gets a task and decodes create_date", async () => {
    const task = await client.tasks.get(requiredId(taskId, "task"));
    expect(task.name).toBe(`TS task ${suffix}`);
    expect(task.create_date).toBeInstanceOf(Date);
  });

  it("tasks: updates task priority", async () => {
    const id = requiredId(taskId, "task");
    await expect(client.tasks.set(id, { priority: "1" })).resolves.toBe(true);
    expect((await client.tasks.get(id, ["priority"])).priority).toBe("1");
  });

  it("tasks: gets task field metadata", async () => {
    await expect(client.tasks.fields()).resolves.toHaveProperty("name");
  });

  it("tasks: builds a task URL", () => {
    const id = requiredId(taskId, "task");
    expect(client.tasks.url(id)).toContain(`id=${id}&model=project.task`);
  });

  it("tasks: posts a comment and returns its message ID", async () => {
    const messageId = await client.tasks.commentWithId(
      requiredId(taskId, "task"),
      `TS task comment ${suffix}`,
      { userId: uid },
    );
    expect(messageId).toBeGreaterThan(0);
  });

  it("tasks: posts an internal note and returns its message ID", async () => {
    const messageId = await client.tasks.noteWithId(
      requiredId(taskId, "task"),
      `TS task note ${suffix}`,
      { userId: uid },
    );
    expect(messageId).toBeGreaterThan(0);
  });

  it("tasks: lists posted messages", async () => {
    const messages = await client.tasks.messages(requiredId(taskId, "task"));
    expect(
      messages.some((record) =>
        String(record.body).includes(`TS task comment ${suffix}`),
      ),
    ).toBe(true);
  });

  it("tasks: creates a tag", async () => {
    taskTagId = await client.tasks.createTag(`TS task tag ${suffix}`, 3);
    expect(taskTagId).toBeGreaterThan(0);
  });

  it("tasks: lists tags", async () => {
    const tags = await client.tasks.tags();
    expectRecordNamed(
      tags,
      requiredId(taskTagId, "task tag"),
      `TS task tag ${suffix}`,
    );
  });

  it("tasks: adds a tag", async () => {
    const id = requiredId(taskId, "task");
    const tagId = requiredId(taskTagId, "task tag");
    await expect(client.tasks.addTag(id, tagId)).resolves.toBe(true);
    expect((await client.tasks.get(id, ["tag_ids"])).tag_ids).toContain(tagId);
  });

  it("tasks: attaches binary bytes", async () => {
    const attachmentId = await createAttachment(
      "project.task",
      requiredId(taskId, "task"),
      [0, 1, 2, 255],
      `task-${suffix}.bin`,
    );
    expect(attachmentId).toBeGreaterThan(0);
  });

  it("tasks: lists attachment metadata", async () => {
    const attachments = await client.tasks.attachments(
      requiredId(taskId, "task"),
    );
    expect(
      attachments.some(
        (record) => String(record.name) === `task-${suffix}.bin`,
      ),
    ).toBe(true);
    expect(attachments[0]?.create_date).toBeInstanceOf(Date);
  });

  it("tasks: downloads one attachment as bytes", async () => {
    const attachmentId = [...attachmentIds].find((candidate) => candidate > 0);
    expect(attachmentId).toBeDefined();
    if (attachmentId !== undefined) {
      const data = await client.tasks.attachmentData(attachmentId);
      expect(data).toBeInstanceOf(Uint8Array);
    }
  });

  it("tasks: returns all record attachment data", async () => {
    const attachments = await client.tasks.allAttachmentData(
      requiredId(taskId, "task"),
    );
    const item = attachments.find(
      (candidate) => candidate.name === `task-${suffix}.bin`,
    );
    expect(item === undefined ? undefined : [...item.data]).toEqual([
      0, 1, 2, 255,
    ]);
  });

  it("tasks: filters downloaded attachments by extension", async () => {
    const attachments = await client.tasks.download(
      requiredId(taskId, "task"),
      "bin",
    );
    expect(attachments.every((item) => item.name.endsWith(".bin"))).toBe(true);
    expect(attachments.some((item) => item.name === `task-${suffix}.bin`)).toBe(
      true,
    );
  });

  it("tasks: preserves a zero-byte attachment", async () => {
    const attachmentId = await client.tasks.attach(
      requiredId(taskId, "task"),
      new Uint8Array(),
      `empty-${suffix}.bin`,
    );
    attachmentIds.add(attachmentId);
    await expect(
      client.tasks.attachmentData(attachmentId),
    ).resolves.toHaveLength(0);
  });

  it("tasks: creates a subtask", async () => {
    subtaskId = await client.tasks.create(
      `TS subtask ${suffix}`,
      requiredId(projectId, "project"),
      { parentId: requiredId(taskId, "task") },
    );
    const subtask = await client.tasks.get(subtaskId, ["name", "parent_id"]);
    expect(relationId(subtask.parent_id)).toBe(taskId);
  });

  it.skipIf(!enterprise)(
    "tasks: schedules start and deadline dates",
    async () => {
      const id = requiredId(taskId, "task");
      await expect(
        client.tasks.schedule(
          id,
          new Date("2026-04-01T09:30:00.000Z"),
          new Date("2026-04-30T00:00:00.000Z"),
        ),
      ).resolves.toBe(true);
      const task = await client.tasks.get(id, [
        "planned_date_begin",
        "date_deadline",
      ]);
      expect(String(task.planned_date_begin)).toContain("2026-04-01");
      expect(String(task.date_deadline)).toContain("2026-04-30");
    },
  );

  it("tasks: assigns a same-project milestone", async () => {
    await expect(
      client.tasks.setMilestone(
        requiredId(taskId, "task"),
        requiredId(milestoneId, "milestone"),
      ),
    ).resolves.toBe(true);
  });

  it("projects: lists tasks assigned to a milestone", async () => {
    const tasks = await client.projects.milestoneTasks(
      requiredId(milestoneId, "milestone"),
    );
    expect(tasks.some((candidate) => candidate.id === taskId)).toBe(true);
  });

  it("projects: marks a milestone reached", async () => {
    await expect(
      client.projects.reachMilestone(requiredId(milestoneId, "milestone")),
    ).resolves.toBe(true);
  });

  it("crm: creates an opportunity", async () => {
    leadId = await client.crm.create(`TS opportunity ${suffix}`, {
      expectedRevenue: 1234.5,
    });
    expect(leadId).toBeGreaterThan(0);
  });

  it("crm: lists opportunities", async () => {
    const id = requiredId(leadId, "lead");
    expectRecordNamed(
      await client.crm.list({ domain: [["id", "=", id]] }),
      id,
      `TS opportunity ${suffix}`,
    );
  });

  it("crm: gets an opportunity and decodes create_date", async () => {
    const lead = await client.crm.get(requiredId(leadId, "lead"));
    expect(lead.name).toBe(`TS opportunity ${suffix}`);
    expect(lead.create_date).toBeInstanceOf(Date);
  });

  it("crm: normalizes an empty partner relation to null", async () => {
    const lead = await client.crm.get(requiredId(leadId, "lead"), [
      "partner_id",
    ]);
    expect(lead.partner_id).toBeNull();
  });

  it("crm: updates opportunity fields", async () => {
    const id = requiredId(leadId, "lead");
    await expect(client.crm.set(id, { priority: "2" })).resolves.toBe(true);
    expect((await client.crm.get(id, ["priority"])).priority).toBe("2");
  });

  it("crm: gets field metadata", async () => {
    await expect(client.crm.fields()).resolves.toHaveProperty("name");
  });

  it("crm: builds an opportunity URL", () => {
    const id = requiredId(leadId, "lead");
    expect(client.crm.url(id)).toContain(`id=${id}&model=crm.lead`);
  });

  it("crm: posts and lists a comment", async () => {
    const id = requiredId(leadId, "lead");
    const body = `TS CRM comment ${suffix}`;
    await expect(client.crm.comment(id, body, { userId: uid })).resolves.toBe(
      true,
    );
    expect(
      (await client.crm.messages(id)).some((record) =>
        String(record.body).includes(body),
      ),
    ).toBe(true);
  });

  it("crm: posts an internal note", async () => {
    await expect(
      client.crm.note(requiredId(leadId, "lead"), `TS CRM note ${suffix}`, {
        userId: uid,
      }),
    ).resolves.toBe(true);
  });

  it("crm: creates and lists a tag", async () => {
    crmTagId = await client.create("crm.tag", { name: `TS CRM tag ${suffix}` });
    expectRecordNamed(
      await client.crm.tags(),
      crmTagId,
      `TS CRM tag ${suffix}`,
    );
  });

  it("crm: adds a tag", async () => {
    const id = requiredId(leadId, "lead");
    const tagId = requiredId(crmTagId, "CRM tag");
    await expect(client.crm.addTag(id, tagId)).resolves.toBe(true);
    expect((await client.crm.get(id, ["tag_ids"])).tag_ids).toContain(tagId);
  });

  it("crm: creates an opportunity with tags", async () => {
    const taggedLeadId = await client.crm.create(
      `TS tagged opportunity ${suffix}`,
      {
        tagIds: [requiredId(crmTagId, "CRM tag")],
      },
    );
    try {
      expect(
        (await client.crm.get(taggedLeadId, ["tag_ids"])).tag_ids,
      ).toContain(crmTagId);
    } finally {
      await client.unlink("crm.lead", [taggedLeadId]);
    }
  });

  it("crm: round-trips attachment bytes", async () => {
    const attachmentId = await createAttachment(
      "crm.lead",
      requiredId(leadId, "lead"),
      [67, 82, 77],
      `crm-${suffix}.bin`,
    );
    expect([...(await client.crm.attachmentData(attachmentId))]).toEqual([
      67, 82, 77,
    ]);
  });

  it("crm: lists stages", async () => {
    const stages = await client.crm.stages();
    expect(stages.length).toBeGreaterThan(0);
  });

  it("crm: builds a pipeline summary containing the fixture", async () => {
    const summary = await client.crm.pipeline();
    expect(summary.deals.some((deal) => deal.id === leadId)).toBe(true);
    expect(summary.totals.deals).toBeGreaterThan(0);
  });

  it("crm: computes pipeline health flags", async () => {
    const flags = computeHealthFlags(await client.crm.pipeline());
    expect(flags.some((flag) => flag.dealId === leadId)).toBe(true);
  });

  it("activities: lists project-task activities", async () => {
    const activities = await client.activities.list({
      domain: [["res_model", "=", "project.task"]],
      limit: 2,
    });
    expect(Array.isArray(activities)).toBe(true);
  });

  it("activities: gets field metadata", async () => {
    await expect(client.activities.fields()).resolves.toHaveProperty(
      "res_model",
    );
  });

  it("account moves: model is installed", async () => {
    const ids = await client.search("ir.model", {
      domain: [["model", "=", "account.move"]],
      limit: 1,
    });
    expect(ids).toHaveLength(1);
  });

  it("account moves: creates a balanced draft entry", async () => {
    accountMoveId = await createAccountMove();
    expect(accountMoveId).toBeGreaterThan(0);
  });

  it("account moves: lists the fixture and decodes its date", async () => {
    const id = requiredId(accountMoveId, "account move");
    const moves = await client.accountMoves.list({ domain: [["id", "=", id]] });
    expect(moves.map((move) => move.id)).toContain(id);
    expect(moves[0]?.date).toBeInstanceOf(Date);
  });

  it("account moves: gets the fixture", async () => {
    const id = requiredId(accountMoveId, "account move");
    expect((await client.accountMoves.get(id)).id).toBe(id);
  });

  it("account moves: builds a form URL", () => {
    const id = requiredId(accountMoveId, "account move");
    expect(client.accountMoves.url(id)).toContain(
      `id=${id}&model=account.move`,
    );
  });

  it("account moves: round-trips attachment bytes", async () => {
    const attachmentId = await client.accountMoves.attach(
      requiredId(accountMoveId, "account move"),
      new Uint8Array([65, 67, 67]),
      `account-move-${suffix}.bin`,
    );
    attachmentIds.add(attachmentId);
    expect([
      ...(await client.accountMoves.attachmentData(attachmentId)),
    ]).toEqual([65, 67, 67]);
  });

  it("account moves: gets field metadata", async () => {
    await expect(client.accountMoves.fields()).resolves.toHaveProperty("date");
  });

  it("security: reads the authenticated user", async () => {
    const user = await client.security.getUser(uid);
    expect(user.login).toBe(config.username);
  });

  it("security: resolves a user by login", async () => {
    await expect(
      client.security.resolveUser({ login: config.username }),
    ).resolves.toBe(uid);
  });

  it("security: creates a user", async () => {
    const result = await client.security.createUser(
      `TS user ${suffix}`,
      `ts-${suffix}@example.invalid`,
      { password: `Vodoo-${suffix}-A1!` },
    );
    securityUserId = result.userId;
    expect(result.password).toBe(`Vodoo-${suffix}-A1!`);
    expect((await client.security.getUser(result.userId)).login).toBe(
      `ts-${suffix}@example.invalid`,
    );
  });

  it("security: sets an explicit password", async () => {
    await expect(
      client.security.setPassword(
        requiredId(securityUserId, "security user"),
        `Changed-${suffix}-A1!`,
      ),
    ).resolves.toBe(`Changed-${suffix}-A1!`);
  });

  it("errors: raises a typed record-not-found error", async () => {
    const promise = client.projects.get(2_147_483_647);
    await expect(promise).rejects.toBeInstanceOf(RecordNotFoundError);
  });

  it("errors: record-not-found remains a VodooError", async () => {
    try {
      await client.tasks.get(2_147_483_647);
      throw new Error("expected missing task");
    } catch (error) {
      expect(error).toBeInstanceOf(VodooError);
    }
  });

  describe.skipIf(!enterprise)("Enterprise namespaces", () => {
    it("helpdesk: creates a ticket", async () => {
      ticketId = await client.helpdesk.create(`TS ticket ${suffix}`, {
        description: "Created by the TypeScript integration suite",
      });
      expect(ticketId).toBeGreaterThan(0);
    });

    it("helpdesk: lists tickets", async () => {
      const id = requiredId(ticketId, "ticket");
      expectRecordNamed(
        await client.helpdesk.list({ domain: [["id", "=", id]] }),
        id,
        `TS ticket ${suffix}`,
      );
    });

    it("helpdesk: gets a ticket and decodes create_date", async () => {
      const ticket = await client.helpdesk.get(requiredId(ticketId, "ticket"));
      expect(ticket.name).toBe(`TS ticket ${suffix}`);
      expect(ticket.create_date).toBeInstanceOf(Date);
    });

    it("helpdesk: updates ticket priority", async () => {
      const id = requiredId(ticketId, "ticket");
      await expect(client.helpdesk.set(id, { priority: "2" })).resolves.toBe(
        true,
      );
      expect((await client.helpdesk.get(id, ["priority"])).priority).toBe("2");
    });

    it("helpdesk: gets field metadata", async () => {
      await expect(client.helpdesk.fields()).resolves.toHaveProperty("name");
    });

    it("helpdesk: builds a ticket URL", () => {
      const id = requiredId(ticketId, "ticket");
      expect(client.helpdesk.url(id)).toContain(
        `id=${id}&model=helpdesk.ticket`,
      );
    });

    it("helpdesk: posts and lists a comment", async () => {
      const id = requiredId(ticketId, "ticket");
      const body = `TS ticket comment ${suffix}`;
      await expect(
        client.helpdesk.comment(id, body, { userId: uid }),
      ).resolves.toBe(true);
      expect(
        (await client.helpdesk.messages(id)).some((record) =>
          String(record.body).includes(body),
        ),
      ).toBe(true);
    });

    it("helpdesk: posts an internal note", async () => {
      await expect(
        client.helpdesk.note(
          requiredId(ticketId, "ticket"),
          `TS ticket note ${suffix}`,
          {
            userId: uid,
          },
        ),
      ).resolves.toBe(true);
    });

    it("helpdesk: creates, lists, and adds a tag", async () => {
      helpdeskTagId = await client.create("helpdesk.tag", {
        name: `TS helpdesk tag ${suffix}`,
      });
      expectRecordNamed(
        await client.helpdesk.tags(),
        helpdeskTagId,
        `TS helpdesk tag ${suffix}`,
      );
      await expect(
        client.helpdesk.addTag(requiredId(ticketId, "ticket"), helpdeskTagId),
      ).resolves.toBe(true);
    });

    it("helpdesk: round-trips attachment bytes", async () => {
      const attachmentId = await createAttachment(
        "helpdesk.ticket",
        requiredId(ticketId, "ticket"),
        [72, 69, 76, 80],
        `helpdesk-${suffix}.bin`,
      );
      expect([...(await client.helpdesk.attachmentData(attachmentId))]).toEqual(
        [72, 69, 76, 80],
      );
    });

    it("helpdesk: gets all attachment data", async () => {
      const attachments = await client.helpdesk.allAttachmentData(
        requiredId(ticketId, "ticket"),
      );
      expect(
        attachments.some((item) => item.name === `helpdesk-${suffix}.bin`),
      ).toBe(true);
    });

    it("helpdesk: creates a ticket with tags", async () => {
      const taggedTicketId = await client.helpdesk.create(
        `TS tagged ticket ${suffix}`,
        {
          tagIds: [requiredId(helpdeskTagId, "helpdesk tag")],
        },
      );
      try {
        expect(
          (await client.helpdesk.get(taggedTicketId, ["tag_ids"])).tag_ids,
        ).toContain(helpdeskTagId);
      } finally {
        await client.unlink("helpdesk.ticket", [taggedTicketId]);
      }
    });

    it("knowledge: creates an article", async () => {
      articleId = await client.knowledge.create(`TS article ${suffix}`, {
        body: "# TypeScript integration",
      });
      expect(articleId).toBeGreaterThan(0);
    });

    it("knowledge: lists articles", async () => {
      const id = requiredId(articleId, "article");
      expectRecordNamed(
        await client.knowledge.list({ domain: [["id", "=", id]] }),
        id,
        `TS article ${suffix}`,
      );
    });

    it("knowledge: gets article body and write date", async () => {
      const article = await client.knowledge.get(
        requiredId(articleId, "article"),
      );
      expect(String(article.body)).toContain("TypeScript integration");
      expect(article.write_date).toBeInstanceOf(Date);
    });

    it("knowledge: resolves the server article URL", async () => {
      const id = requiredId(articleId, "article");
      expect(await client.knowledge.resolveUrl(id)).toContain(String(id));
    });

    it("knowledge: posts and lists a comment", async () => {
      const id = requiredId(articleId, "article");
      const body = `TS article comment ${suffix}`;
      await expect(
        client.knowledge.comment(id, body, { userId: uid }),
      ).resolves.toBe(true);
      expect(
        (await client.knowledge.messages(id)).some((record) =>
          String(record.body).includes(body),
        ),
      ).toBe(true);
    });

    it("knowledge: posts an internal note", async () => {
      await expect(
        client.knowledge.note(
          requiredId(articleId, "article"),
          `TS article note ${suffix}`,
          {
            userId: uid,
          },
        ),
      ).resolves.toBe(true);
    });

    it("knowledge: round-trips attachment bytes", async () => {
      const attachmentId = await createAttachment(
        "knowledge.article",
        requiredId(articleId, "article"),
        [75, 78],
        `knowledge-${suffix}.bin`,
      );
      expect([
        ...(await client.knowledge.attachmentData(attachmentId)),
      ]).toEqual([75, 78]);
    });

    it("documents: creates a version-appropriate folder", async () => {
      const fields = await client.fieldsGet(
        "documents.document",
        ["type"],
        ["selection"],
      );
      const selection =
        typeof fields.type === "object" && fields.type !== null
          ? (fields.type as Record<string, unknown>).selection
          : undefined;
      const modern = Array.isArray(selection)
        ? selection.some(
            (option) => Array.isArray(option) && option[0] === "folder",
          )
        : typeof selection === "object" &&
          selection !== null &&
          Object.hasOwn(selection, "folder");
      folderModel = modern ? "documents.document" : "documents.folder";
      folderId = await client.create(
        folderModel,
        modern
          ? { name: `TS folder ${suffix}`, type: "folder" }
          : { name: `TS folder ${suffix}` },
      );
      expect(folderId).toBeGreaterThan(0);
    });

    it("documents: discovers the created folder", async () => {
      const folders = await client.documents.folders();
      expectRecordNamed(
        folders,
        requiredId(folderId, "folder"),
        `TS folder ${suffix}`,
      );
    });

    it("documents: resolves the folder by exact name", async () => {
      await expect(
        client.documents.resolveFolder(`TS folder ${suffix}`),
      ).resolves.toBe(requiredId(folderId, "folder"));
    });

    it("documents: uploads bytes with a detected mimetype", async () => {
      documentId = await client.documents.upload(
        new Uint8Array([84, 83]),
        `typescript-${suffix}.txt`,
        { folderId: requiredId(folderId, "folder") },
      );
      expect(documentId).toBeGreaterThan(0);
      expect(
        (await client.documents.get(documentId, ["mimetype"])).mimetype,
      ).toBe("text/plain");
    });

    it("documents: preserves the selected folder", async () => {
      const document = await client.documents.get(
        requiredId(documentId, "document"),
        ["folder_id"],
      );
      expect(relationId(document.folder_id)).toBe(folderId);
    });

    it("documents: downloads exact bytes", async () => {
      const downloaded = await client.documents.downloadFile(
        requiredId(documentId, "document"),
      );
      expect([...downloaded.data]).toEqual([84, 83]);
      expect(downloaded.name).toBe(`typescript-${suffix}.txt`);
    });

    it("timer: creates a timesheet-enabled project and task", async () => {
      timerProjectId = await client.create("project.project", {
        name: `TS timer project ${suffix}`,
        allow_timesheets: true,
      });
      timerTaskId = await client.tasks.create(
        `TS timer task ${suffix}`,
        timerProjectId,
      );
      expect(timerTaskId).toBeGreaterThan(0);
    });

    it("timer: starts a task timer and returns a handle", async () => {
      timerHandle = await client.timer.startTask(
        requiredId(timerTaskId, "timer task"),
      );
      expect(timerHandle).toBeDefined();
    });

    it("timer: lists the active task timer", async () => {
      const active = await client.timer.active();
      const fixtureTimer = active.find(
        (timesheet) =>
          timesheet.source.kind === "task" &&
          timesheet.source.id === timerTaskId,
      );
      if (fixtureTimer !== undefined) timerTimesheetIds.add(fixtureTimer.id);
      expect(fixtureTimer).toBeDefined();
    });

    it("timer: lists typed timesheets", async () => {
      const timesheets = await client.timer.list({ days: 0, limit: 20 });
      const timesheet = timesheets.find(
        (candidate) =>
          candidate.source.kind === "task" &&
          candidate.source.id === timerTaskId,
      );
      if (timesheet !== undefined) timerTimesheetIds.add(timesheet.id);
      expect(timesheet?.date).toBeInstanceOf(Date);
      expect(timesheet?.toObject().state).toBe("running");
    });

    it("timer: handle stops only its target timer", async () => {
      if (timerHandle === null)
        throw new Error("timer handle fixture was not created");
      await timerHandle.stop();
      const active = await client.timer.active();
      expect(
        active.some(
          (timesheet) =>
            timesheet.source.kind === "task" &&
            timesheet.source.id === timerTaskId,
        ),
      ).toBe(false);
    });

    it("timer: a stopped handle rejects a second stop", async () => {
      if (timerHandle === null)
        throw new Error("timer handle fixture was not created");
      await expect(timerHandle.stop()).rejects.toBeInstanceOf(VodooError);
    });
  });
});
