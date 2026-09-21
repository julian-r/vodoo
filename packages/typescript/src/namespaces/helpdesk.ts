import type { OdooClientApi } from "../client-api.js";
import { Cmd } from "../commands.js";
import { GeneratedHelpdeskNamespace } from "../generated/helpdesk.js";
import type { OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

export interface HelpdeskRecord extends OdooRecord {
  id: number;
  name: string;
  create_date?: Date | null;
}

export interface CreateTicketOptions {
  description?: string;
  partnerId?: number;
  tagIds?: readonly number[];
  teamId?: number;
  extraFields?: Readonly<Record<string, unknown>>;
}

export class HelpdeskNamespace extends GeneratedHelpdeskNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<HelpdeskRecord[]> {
    return (await super.list(options)) as HelpdeskRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<HelpdeskRecord> {
    return (await super.get(recordId, fields)) as HelpdeskRecord;
  }

  create(name: string, options: CreateTicketOptions = {}): Promise<number> {
    const values: Record<string, unknown> = {
      ...options.extraFields,
      name,
    };
    if (options.description !== undefined) {
      values.description = options.description;
    }
    if (options.partnerId !== undefined) values.partner_id = options.partnerId;
    if (options.tagIds !== undefined)
      values.tag_ids = [Cmd.set(options.tagIds)];
    if (options.teamId !== undefined) values.team_id = options.teamId;
    return this.client.create("helpdesk.ticket", values);
  }
}
