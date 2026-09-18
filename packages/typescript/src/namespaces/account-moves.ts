import type { OdooClientApi } from "../client-api.js";
import { GeneratedAccountMoveNamespace } from "../generated/account_moves.js";
import type { Domain, OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

export interface AccountMoveRecord extends OdooRecord {
  id: number;
  name: string;
  date?: Date | null;
  invoice_date?: Date | null;
  invoice_date_due?: Date | null;
  create_date?: Date | null;
  write_date?: Date | null;
}

export interface AccountMoveDomainOptions {
  search?: string;
  company?: string;
  companyId?: number;
  partner?: string;
  moveType?: string;
  state?: string;
  year?: number;
}

export function buildAccountMoveDomain(
  options: AccountMoveDomainOptions = {},
): Domain {
  const domain: Array<Domain[number]> = [];
  if (options.search !== undefined && options.search !== "") {
    const fields = ["name", "ref", "payment_reference", "invoice_origin"];
    domain.push("|", "|", "|");
    for (const field of fields) domain.push([field, "ilike", options.search]);
  }
  if (options.company !== undefined && options.company !== "") {
    domain.push(["company_id.name", "ilike", options.company]);
  }
  if (options.companyId !== undefined) {
    domain.push(["company_id", "=", options.companyId]);
  }
  if (options.partner !== undefined && options.partner !== "") {
    domain.push(["partner_id.name", "ilike", options.partner]);
  }
  if (options.moveType !== undefined && options.moveType !== "") {
    domain.push(["move_type", "=", options.moveType]);
  }
  if (options.state !== undefined && options.state !== "") {
    domain.push(["state", "=", options.state]);
  }
  if (options.year !== undefined) {
    const year = String(options.year).padStart(4, "0");
    domain.push(["date", ">=", `${year}-01-01`]);
    domain.push(["date", "<=", `${year}-12-31`]);
  }
  return domain;
}

export class AccountMoveNamespace extends GeneratedAccountMoveNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<AccountMoveRecord[]> {
    return (await super.list(options)) as AccountMoveRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<AccountMoveRecord> {
    return (await super.get(recordId, fields)) as AccountMoveRecord;
  }
}
