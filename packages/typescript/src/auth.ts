import type { OdooClientApi } from "./client-api.js";
import { ConfigurationError, RecordNotFoundError } from "./errors.js";

function relationId(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
}

/** Resolve the configured user (or an explicit login) for requested-author messages. */
export async function getDefaultUserId(
  client: OdooClientApi,
  username = client.username,
): Promise<number> {
  const ids = await client.search("res.users", {
    domain: [["login", "=", username]],
    limit: 1,
  });
  if (ids[0] === undefined) throw new RecordNotFoundError("res.users", 0);
  return ids[0];
}

/** Resolve the partner used as mail.message.author_id for an Odoo user. */
export async function getPartnerIdFromUser(
  client: OdooClientApi,
  userId: number,
): Promise<number> {
  const users = await client.read("res.users", [userId], ["partner_id"]);
  if (users[0] === undefined)
    throw new RecordNotFoundError("res.users", userId);
  const partnerId = relationId(users[0].partner_id);
  if (partnerId === null) throw new RecordNotFoundError("res.partner", 0);
  return partnerId;
}

export interface SudoMessageOptions {
  userId?: number;
  messageType?: string;
  isNote?: boolean;
  extraValues?: Readonly<Record<string, unknown>>;
}

/**
 * Post pre-rendered HTML requesting a selected user's partner as displayed author.
 * Cross-user attribution requires an internal authenticated user. Odoo may reject or
 * override it for share users, which can reliably attribute only to their own partner.
 * This does not change authenticated identity, access checks, or auditing.
 */
export async function messagePostSudoWithId(
  client: OdooClientApi,
  model: string,
  recordId: number,
  body: string,
  options: SudoMessageOptions = {},
): Promise<number> {
  const userId = options.userId ?? client.defaultUserId;
  if (userId === undefined)
    throw new ConfigurationError("No default user ID configured");
  const partnerId = await getPartnerIdFromUser(client, userId);
  const subtypeXmlId = options.isNote === true ? "mt_note" : "mt_comment";
  // The public resolver checks subtype access, not metadata-table read access.
  const reference = await client.execute(
    "ir.model.data",
    "check_object_reference",
    [],
    {
      module: "mail",
      xml_id: subtypeXmlId,
      raise_on_access_error: true,
    },
  );
  const subtypeId: unknown = Array.isArray(reference)
    ? reference[1]
    : undefined;
  if (
    !Array.isArray(reference) ||
    reference.length !== 2 ||
    reference[0] !== "mail.message.subtype" ||
    typeof subtypeId !== "number" ||
    !Number.isInteger(subtypeId) ||
    subtypeId <= 0
  ) {
    throw new RecordNotFoundError("mail.message.subtype", 0);
  }
  return client.create("mail.message", {
    ...options.extraValues,
    model,
    res_id: recordId,
    body,
    message_type:
      options.isNote === true
        ? "notification"
        : (options.messageType ?? "comment"),
    subtype_id: subtypeId,
    author_id: partnerId,
  });
}

/**
 * Post pre-rendered HTML requesting selected-user author attribution.
 * Cross-user attribution requires an internal authenticated user. Odoo may reject or
 * override it for share users, which can reliably attribute only to their own partner.
 * This does not change authenticated identity, access checks, or auditing.
 */
export async function messagePostSudo(
  client: OdooClientApi,
  model: string,
  recordId: number,
  body: string,
  options: SudoMessageOptions = {},
): Promise<boolean> {
  return (
    (await messagePostSudoWithId(client, model, recordId, body, options)) > 0
  );
}
