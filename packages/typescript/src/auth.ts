import type { OdooClientApi } from "./client-api.js";
import { ConfigurationError, RecordNotFoundError } from "./errors.js";

function relationId(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
}

/** Resolve the configured user (or an explicit login) for author-attributed messages. */
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
 * Post pre-rendered HTML with a selected user's partner as the displayed author.
 * This does not change the authenticated execution identity, access checks, or auditing.
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
  const subtypeName = options.isNote === true ? "Note" : "Discussions";
  const subtypeIds = await client.search("mail.message.subtype", {
    domain: [["name", "=", subtypeName]],
    limit: 1,
  });
  return client.create("mail.message", {
    ...options.extraValues,
    model,
    res_id: recordId,
    body,
    message_type:
      options.isNote === true
        ? "notification"
        : (options.messageType ?? "comment"),
    subtype_id: subtypeIds[0] ?? false,
    author_id: partnerId,
  });
}

/**
 * Post pre-rendered HTML with selected-user author attribution.
 * This does not change the authenticated execution identity, access checks, or auditing.
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
