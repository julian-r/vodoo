import type { OdooClientApi } from "../client-api.js";
import { Cmd } from "../commands.js";
import { richTextToHtml } from "../content.js";
import type { RichText } from "../content.js";
import { formatOdooDate, formatOdooDateTime } from "../dates.js";
import { RecordNotFoundError, RecordOperationError } from "../errors.js";
import { GeneratedTaskNamespace } from "../generated/project_tasks.js";
import type { OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

export interface TaskRecord extends OdooRecord {
  id: number;
  name: string;
  create_date?: Date | null;
}

export interface CreateTaskOptions {
  description?: RichText;
  userIds?: readonly number[];
  tagIds?: readonly number[];
  parentId?: number;
  extraFields?: Readonly<Record<string, unknown>>;
}

function relationId(value: unknown): number | null {
  if (typeof value === "number" && !Number.isNaN(value)) return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
}

export class TaskNamespace extends GeneratedTaskNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<TaskRecord[]> {
    return (await super.list(options)) as TaskRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<TaskRecord> {
    return (await super.get(recordId, fields)) as TaskRecord;
  }

  create(
    name: string,
    projectId: number,
    options: CreateTaskOptions = {},
  ): Promise<number> {
    const values: Record<string, unknown> = {
      ...options.extraFields,
      name,
      project_id: projectId,
    };
    if (
      options.description !== undefined &&
      String(options.description) !== ""
    ) {
      values.description = richTextToHtml(options.description);
    }
    if (options.userIds !== undefined && options.userIds.length > 0) {
      values.user_ids = [Cmd.set(options.userIds)];
    }
    if (options.tagIds !== undefined && options.tagIds.length > 0) {
      values.tag_ids = [Cmd.set(options.tagIds)];
    }
    if (options.parentId !== undefined && options.parentId !== 0) {
      values.parent_id = options.parentId;
    }
    return this.client.create("project.task", values, {
      default_project_id: projectId,
    });
  }

  async setMilestone(taskId: number, milestoneId: number): Promise<boolean> {
    const tasks = await this.client.read(
      "project.task",
      [taskId],
      ["project_id"],
    );
    if (tasks.length === 0) {
      throw new RecordNotFoundError("project.task", taskId);
    }
    const milestones = await this.client.read(
      "project.milestone",
      [milestoneId],
      ["project_id"],
    );
    if (milestones.length === 0) {
      throw new RecordNotFoundError("project.milestone", milestoneId);
    }
    const taskProjectId = relationId(tasks[0]?.project_id);
    const milestoneProjectId = relationId(milestones[0]?.project_id);
    if (taskProjectId === null || milestoneProjectId === null) {
      throw new RecordOperationError(
        "Task and milestone must both belong to a project",
      );
    }
    if (taskProjectId !== milestoneProjectId) {
      throw new RecordOperationError(
        `Task ${taskId} and milestone ${milestoneId} belong to different projects`,
      );
    }
    return this.client.write("project.task", [taskId], {
      milestone_id: milestoneId,
    });
  }

  addDependencies(
    taskId: number,
    dependencyIds: readonly number[],
  ): Promise<boolean> {
    return this.set(taskId, {
      depend_on_ids: dependencyIds.map((dependencyId) =>
        Cmd.link(dependencyId),
      ),
    });
  }

  clearDependencies(taskId: number): Promise<boolean> {
    return this.set(taskId, { depend_on_ids: [Cmd.clear()] });
  }

  schedule(taskId: number, start: Date, end: Date): Promise<boolean> {
    return this.set(taskId, {
      planned_date_begin: formatOdooDateTime(start),
      date_deadline: formatOdooDate(end),
    });
  }

  createTag(name: string, color?: number): Promise<number> {
    const values: Record<string, unknown> = { name };
    if (color !== undefined) values.color = color;
    return this.client.create("project.tags", values);
  }

  deleteTag(tagId: number): Promise<boolean> {
    return this.client.unlink("project.tags", [tagId]);
  }
}
