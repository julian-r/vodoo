import type { OdooClientApi } from "../client-api.js";
import { RecordOperationError } from "../errors.js";
import { GeneratedActivityNamespace } from "../generated/activities.js";
import type { Domain, OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

export interface ActivityRecord extends OdooRecord {
  id: number;
  date_deadline?: Date | null;
  create_date?: Date | null;
  write_date?: Date | null;
}

export interface ActivityDomainOptions {
  model?: string;
  user?: string;
  activityType?: string;
}

export function buildActivityDomain(
  options: ActivityDomainOptions = {},
): Domain {
  const domain: Array<Domain[number]> = [];
  if (options.model !== undefined && options.model !== "") {
    domain.push(["res_model", "=", options.model]);
  }
  if (options.user !== undefined && options.user !== "") {
    domain.push(["user_id.name", "ilike", options.user]);
  }
  if (options.activityType !== undefined && options.activityType !== "") {
    domain.push(["activity_type_id.name", "ilike", options.activityType]);
  }
  return domain;
}

export class ActivityNamespace extends GeneratedActivityNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<ActivityRecord[]> {
    return (await super.list(options)) as ActivityRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<ActivityRecord> {
    return (await super.get(recordId, fields)) as ActivityRecord;
  }

  async done(activityId: number): Promise<unknown> {
    const activity = await this.get(activityId, ["active"]);
    if (!activity.active) {
      throw new RecordOperationError(`Activity ${activityId} is already done`);
    }
    return this.client.execute("mail.activity", "action_done", [[activityId]]);
  }
}
