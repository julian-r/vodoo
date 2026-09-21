import type { OdooClientApi } from "../client-api.js";
import { Cmd } from "../commands.js";
import { VodooError } from "../errors.js";
import type { OdooRecord } from "../types.js";
import { GROUP_DEFINITIONS } from "../generated/security_groups.js";

export interface AccessDefinition {
  readonly model: string;
  readonly permRead: boolean;
  readonly permWrite: boolean;
  readonly permCreate: boolean;
  readonly permUnlink: boolean;
}

export interface RuleDefinition extends AccessDefinition {
  readonly domain: string;
}

export interface GroupDefinition {
  readonly name: string;
  readonly comment: string;
  readonly access: readonly AccessDefinition[];
  readonly rules?: readonly RuleDefinition[];
}

const access = (
  model: string,
  permRead: boolean,
  permWrite: boolean,
  permCreate: boolean,
  permUnlink: boolean,
): AccessDefinition => ({ model, permRead, permWrite, permCreate, permUnlink });

const rule = (
  model: string,
  domain: string,
  permRead: boolean,
  permWrite: boolean,
  permCreate: boolean,
  permUnlink: boolean,
): RuleDefinition => ({
  model,
  domain,
  permRead,
  permWrite,
  permCreate,
  permUnlink,
});

const LEGACY_GROUP_DEFINITIONS: readonly GroupDefinition[] = Object.freeze([
  {
    name: "API Mail Gateway",
    comment: "Standalone access for mail gateway (message_process via XML-RPC)",
    access: [
      access("mail.message", true, false, false, false),
      access("mail.message.subtype", true, false, false, false),
      access("mail.alias", true, true, false, false),
      access("mail.alias.domain", true, false, false, false),
      access("mail.followers", true, false, false, false),
      access("res.users", true, false, false, false),
      access("res.partner", true, false, false, false),
      access("ir.model", true, false, false, false),
      access("ir.model.data", true, false, false, false),
    ],
  },
  {
    name: "API Base",
    comment: "Core API access - required for all service accounts",
    access: [
      access("res.company", true, false, false, false),
      access("res.users", true, false, false, false),
      access("res.partner", true, false, false, false),
      access("res.currency", true, false, false, false),
      access("res.country", true, false, false, false),
      access("res.country.state", true, false, false, false),
      access("ir.attachment", true, true, true, false),
      access("mail.message", true, true, true, false),
      access("mail.message.subtype", true, false, false, false),
      access("mail.followers", true, true, true, false),
      access("mail.notification", true, true, true, false),
    ],
    rules: [
      rule("mail.message", "[(1, '=', 1)]", true, true, true, false),
      rule("mail.followers", "[(1, '=', 1)]", true, true, true, false),
      rule("mail.notification", "[(1, '=', 1)]", true, true, true, false),
    ],
  },
  {
    name: "API CRM",
    comment: "CRM leads and opportunities",
    access: [
      access("crm.lead", true, true, true, false),
      access("crm.tag", true, true, true, false),
      access("crm.stage", true, false, false, false),
      access("crm.team", true, false, false, false),
      access("utm.source", true, false, false, false),
      access("utm.medium", true, false, false, false),
      access("utm.campaign", true, false, false, false),
    ],
    rules: [rule("crm.lead", "[(1, '=', 1)]", true, true, true, false)],
  },
  {
    name: "API Project",
    comment: "Projects and tasks (follower-based access)",
    access: [
      access("project.project", true, true, true, false),
      access("project.task", true, true, true, false),
      access("project.task.type", true, false, false, false),
      access("project.tags", true, true, true, false),
      access("project.milestone", true, true, true, false),
    ],
    rules: [
      rule(
        "project.project",
        "[('message_partner_ids', 'in', [user.partner_id.id])]",
        true,
        true,
        true,
        false,
      ),
      rule(
        "project.task",
        "[('project_id.message_partner_ids', 'in', [user.partner_id.id])]",
        true,
        true,
        true,
        false,
      ),
      rule(
        "project.milestone",
        "[('project_id.message_partner_ids', 'in', [user.partner_id.id])]",
        true,
        true,
        true,
        false,
      ),
    ],
  },
  {
    name: "API Knowledge",
    comment: "Knowledge base articles",
    access: [
      access("knowledge.article", true, true, true, false),
      access("knowledge.article.member", true, false, false, false),
    ],
    rules: [
      rule("knowledge.article", "[(1, '=', 1)]", true, true, true, false),
    ],
  },
  {
    name: "API Helpdesk",
    comment: "Helpdesk tickets",
    access: [
      access("helpdesk.ticket", true, true, true, false),
      access("helpdesk.tag", true, true, true, false),
      access("helpdesk.stage", true, false, false, false),
      access("helpdesk.team", true, false, false, false),
      access("helpdesk.ticket.type", true, false, false, false),
      access("helpdesk.sla", true, false, false, false),
    ],
    rules: [rule("helpdesk.ticket", "[(1, '=', 1)]", true, true, true, false)],
  },
]);
void LEGACY_GROUP_DEFINITIONS;

export { GROUP_DEFINITIONS };
export interface GroupResult {
  readonly groupIds: Readonly<Record<string, number>>;
  readonly warnings: readonly string[];
}

export interface CreateUserOptions {
  password?: string;
  email?: string;
}

export interface CreatedUser {
  readonly userId: number;
  readonly password: string;
}

const PASSWORD_ALPHABET =
  "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*";

function generatePassword(): string {
  let password = "";
  const unbiasedLimit =
    Math.floor(256 / PASSWORD_ALPHABET.length) * PASSWORD_ALPHABET.length;
  while (password.length < 24) {
    const random = crypto.getRandomValues(new Uint8Array(24));
    for (const value of random) {
      if (value >= unbiasedLimit) continue;
      password += PASSWORD_ALPHABET[value % PASSWORD_ALPHABET.length];
      if (password.length === 24) break;
    }
  }
  return password;
}

function slugify(value: string): string {
  return value.toLocaleLowerCase("und").replaceAll(" ", "_");
}

function accessName(groupName: string, model: string): string {
  return `vodoo_${slugify(groupName)}_access_${model.replaceAll(".", "_")}`;
}

function ruleName(groupName: string, model: string): string {
  return `vodoo_${slugify(groupName)}_rule_${model.replaceAll(".", "_")}`;
}

export class SecurityNamespace {
  constructor(private readonly client: OdooClientApi) {}

  async createGroups(): Promise<GroupResult> {
    const warnings: string[] = [];
    const groupIds: Record<string, number> = {};
    for (const group of GROUP_DEFINITIONS) {
      const groupId = await this.ensureGroup(group);
      groupIds[group.name] = groupId;
      for (const definition of group.access) {
        const modelId = await this.getModelId(definition.model);
        if (modelId === null) {
          warnings.push(
            `Model '${definition.model}' not found; skipping access`,
          );
          continue;
        }
        await this.ensureAccess(groupId, group.name, modelId, definition);
      }
      for (const definition of group.rules ?? []) {
        const modelId = await this.getModelId(definition.model);
        if (modelId === null) {
          warnings.push(`Model '${definition.model}' not found; skipping rule`);
          continue;
        }
        await this.ensureRule(groupId, group.name, modelId, definition);
      }
    }
    return { groupIds, warnings };
  }

  async getGroupIds(groupNames: readonly string[]): Promise<GroupResult> {
    const warnings: string[] = [];
    const groupIds: Record<string, number> = {};
    for (const name of groupNames) {
      const ids = await this.client.search("res.groups", {
        domain: [["name", "=", name]],
        limit: 1,
      });
      const groupId = ids[0];
      if (groupId === undefined) warnings.push(`Group '${name}' not found`);
      else groupIds[name] = groupId;
    }
    return { groupIds, warnings };
  }

  async assign(
    userId: number,
    groupIds: readonly number[],
    options: { removeDefaultGroups?: boolean } = {},
  ): Promise<void> {
    const commands: unknown[] = [];
    if (options.removeDefaultGroups ?? true) {
      for (const xmlId of ["base.group_user", "base.group_portal"] as const) {
        const groupId = await this.getGroupIdByXmlId(xmlId);
        if (groupId !== null) commands.push(Cmd.unlink(groupId));
      }
    }
    commands.push(...groupIds.map((groupId) => Cmd.link(groupId)));
    const groupsField = await this.groupsField();
    await this.client.write("res.users", [userId], { [groupsField]: commands });
  }

  async resolveUser(options: {
    userId?: number;
    login?: string;
  }): Promise<number> {
    if (options.userId !== undefined) return options.userId;
    if (options.login === undefined || options.login === "") {
      throw new VodooError("Provide userId or login");
    }
    const ids = await this.client.search("res.users", {
      domain: [["login", "=", options.login]],
      limit: 1,
    });
    if (ids[0] === undefined) {
      throw new VodooError(`User with login '${options.login}' not found`);
    }
    return ids[0];
  }

  async createUser(
    name: string,
    login: string,
    options: CreateUserOptions = {},
  ): Promise<CreatedUser> {
    const password = options.password ?? generatePassword();
    const groupsField = await this.groupsField();
    const userId = await this.client.create("res.users", {
      name,
      login,
      email: options.email ?? login,
      password,
      [groupsField]: [Cmd.set([])],
    });
    return { userId, password };
  }

  async setPassword(
    userId: number,
    password = generatePassword(),
  ): Promise<string> {
    await this.client.write("res.users", [userId], { password });
    return password;
  }

  async getUser(userId: number): Promise<OdooRecord> {
    const groupsField = await this.groupsField();
    const users = await this.client.searchRead("res.users", {
      domain: [["id", "=", userId]],
      fields: [
        "name",
        "login",
        "email",
        "active",
        "share",
        groupsField,
        "partner_id",
      ],
      limit: 1,
    });
    if (users[0] === undefined)
      throw new VodooError(`User ${userId} not found`);
    return users[0];
  }

  private async groupsField(): Promise<"group_ids" | "groups_id"> {
    const fields = await this.client.fieldsGet(
      "res.users",
      ["group_ids"],
      ["type"],
    );
    const groupIds = fields.group_ids;
    return typeof groupIds === "object" &&
      groupIds !== null &&
      (groupIds as Record<string, unknown>).type === "many2many"
      ? "group_ids"
      : "groups_id";
  }

  private async ensureGroup(group: GroupDefinition): Promise<number> {
    const ids = await this.client.search("res.groups", {
      domain: [["name", "=", group.name]],
      limit: 1,
    });
    return (
      ids[0] ??
      this.client.create("res.groups", {
        name: group.name,
        comment: group.comment,
      })
    );
  }

  private async ensureAccess(
    groupId: number,
    groupName: string,
    modelId: number,
    definition: AccessDefinition,
  ): Promise<number> {
    const name = accessName(groupName, definition.model);
    const ids = await this.client.search("ir.model.access", {
      domain: [
        ["name", "=", name],
        ["model_id", "=", modelId],
        ["group_id", "=", groupId],
      ],
      limit: 1,
    });
    return (
      ids[0] ??
      this.client.create("ir.model.access", {
        name,
        model_id: modelId,
        group_id: groupId,
        perm_read: definition.permRead,
        perm_write: definition.permWrite,
        perm_create: definition.permCreate,
        perm_unlink: definition.permUnlink,
      })
    );
  }

  private async ensureRule(
    groupId: number,
    groupName: string,
    modelId: number,
    definition: RuleDefinition,
  ): Promise<number> {
    const name = ruleName(groupName, definition.model);
    const ids = await this.client.search("ir.rule", {
      domain: [
        ["name", "=", name],
        ["model_id", "=", modelId],
      ],
      limit: 1,
    });
    return (
      ids[0] ??
      this.client.create("ir.rule", {
        name,
        model_id: modelId,
        groups: [Cmd.link(groupId)],
        domain_force: definition.domain,
        perm_read: definition.permRead,
        perm_write: definition.permWrite,
        perm_create: definition.permCreate,
        perm_unlink: definition.permUnlink,
      })
    );
  }

  private async getModelId(model: string): Promise<number | null> {
    const ids = await this.client.search("ir.model", {
      domain: [["model", "=", model]],
      limit: 1,
    });
    return ids[0] ?? null;
  }

  private async getGroupIdByXmlId(xmlId: string): Promise<number | null> {
    const [module, name] = xmlId.split(".", 2);
    if (module === undefined || name === undefined) return null;
    const records = await this.client.searchRead("ir.model.data", {
      domain: [
        ["module", "=", module],
        ["name", "=", name],
      ],
      fields: ["res_id"],
      limit: 1,
    });
    const value = records[0]?.res_id;
    return typeof value === "number" ? value : null;
  }
}
