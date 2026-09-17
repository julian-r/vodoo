import type { OdooClientApi } from "../client-api.js";
import { decodeRecordDates, formatOdooDate } from "../dates.js";
import { VodooError } from "../errors.js";
import {
  GeneratedProjectNamespace,
  PROJECT_MILESTONES,
} from "../generated/projects.js";
import type { OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

export interface ProjectRecord extends OdooRecord {
  id: number;
  name: string;
  date_start?: Date | null;
  date?: Date | null;
  write_date?: Date | null;
}

export interface ProjectStage extends OdooRecord {
  id: number;
  name: string;
  sequence?: number;
  fold?: boolean | null;
  project_ids?: number[];
}

export interface ProjectMilestone extends OdooRecord {
  id: number;
  name: string;
  project_id?: unknown;
  deadline?: Date | null;
  is_reached?: boolean | null;
  reached_date?: Date | null;
  is_deadline_exceeded?: boolean | null;
}

export interface MilestoneTask extends OdooRecord {
  id: number;
  name: string;
}

const MILESTONE_DATE_FIELDS = {
  deadline: "date",
  reached_date: "date",
} as const;

/** Python-compatible case-insensitive comparison without locale-sensitive matching. */
function caseFold(value: string): string {
  return value
    .toLocaleLowerCase("und")
    .replaceAll("ß", "ss")
    .replaceAll("ẞ", "ss");
}

export class ProjectNamespace extends GeneratedProjectNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<ProjectRecord[]> {
    return (await super.list(options)) as ProjectRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<ProjectRecord> {
    return (await super.get(recordId, fields)) as ProjectRecord;
  }

  override async stages(
    projectId: number | null = null,
  ): Promise<ProjectStage[]> {
    return (await super.stages(projectId)) as ProjectStage[];
  }

  async resolveProjectId(project: number | string): Promise<number> {
    if (typeof project === "number" || /^\d+$/u.test(project)) {
      return Number(project);
    }
    const candidates = await this.client.searchRead("project.project", {
      domain: [["name", "=ilike", project]],
      fields: ["id", "name"],
      order: "id",
    });
    const expected = caseFold(project);
    const matches = candidates.filter(
      (candidate) => caseFold(String(candidate.name ?? "")) === expected,
    );
    if (matches.length === 0) {
      throw new VodooError(`Project '${project}' not found`);
    }
    if (matches.length > 1) {
      throw new VodooError(
        `Project name '${project}' is ambiguous; use a project ID`,
      );
    }
    return Number(matches[0]?.id);
  }

  async milestones(project: number | string): Promise<ProjectMilestone[]> {
    const projectId = await this.resolveProjectId(project);
    const records = await this.client.searchRead("project.milestone", {
      domain: [["project_id", "=", projectId]],
      fields: PROJECT_MILESTONES,
      order: "deadline, id",
    });
    return records.map(
      (record) =>
        decodeRecordDates(record, MILESTONE_DATE_FIELDS) as ProjectMilestone,
    );
  }

  async createMilestone(
    project: number | string,
    name: string,
    deadline: Date,
  ): Promise<number> {
    const projectId = await this.resolveProjectId(project);
    return this.client.create("project.milestone", {
      project_id: projectId,
      name,
      deadline: formatOdooDate(deadline),
    });
  }

  override async milestoneTasks(milestoneId: number): Promise<MilestoneTask[]> {
    return (await super.milestoneTasks(milestoneId)) as MilestoneTask[];
  }
}
