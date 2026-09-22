import type {
  OdooClientApi,
  SearchOptions,
  SearchReadOptions,
} from "./client-api.js";
import { processContentValues } from "./content.js";
import { ConfigurationError, VodooError } from "./errors.js";
import { AccountMoveNamespace } from "./namespaces/account-moves.js";
import { ActivityNamespace } from "./namespaces/activities.js";
import { CRMNamespace } from "./namespaces/crm.js";
import { DocumentNamespace } from "./namespaces/documents.js";
import { GenericNamespace } from "./namespaces/generic.js";
import { HelpdeskNamespace } from "./namespaces/helpdesk.js";
import { KnowledgeNamespace } from "./namespaces/knowledge.js";
import { ProjectNamespace } from "./namespaces/projects.js";
import { SecurityNamespace } from "./namespaces/security.js";
import { TaskNamespace } from "./namespaces/tasks.js";
import { TimerNamespace } from "./namespaces/timer.js";
import {
  JSON2Transport,
  LegacyTransport,
  type OdooTransportApi,
  type TransportOptions,
} from "./transport.js";
import type {
  Domain,
  FetchLike,
  NameSearchResult,
  OdooConfig,
  OdooRecord,
  RetryConfig,
  Sleep,
} from "./types.js";

export type OdooProtocol = "auto" | "json2" | "jsonrpc";

/** Minimum structural contract implemented by a Worker's generated Env type. */
export interface OdooWorkerBindings {
  ODOO_URL: string;
  ODOO_DATABASE: string;
  ODOO_USERNAME: string;
  ODOO_PASSWORD: string;
}

export interface OdooClientOptions {
  transport?: OdooTransportApi;
  protocol?: OdooProtocol;
  /** @deprecated Use `protocol: "jsonrpc"` instead. */
  autoDetect?: boolean;
  fetch?: FetchLike;
  sleep?: Sleep;
}

export interface OdooWorkerClientOptions {
  protocol?: OdooProtocol;
  defaultUserId?: number;
  timeoutMs?: number;
  retry?: Partial<RetryConfig>;
  headers?: Readonly<Record<string, string>>;
  fetch?: FetchLike;
  sleep?: Sleep;
}

function normalizeFalse(records: OdooRecord[]): OdooRecord[] {
  for (const record of records) {
    for (const [key, value] of Object.entries(record)) {
      if (value === false) record[key] = null;
    }
  }
  return records;
}

export class OdooClient implements OdooClientApi {
  readonly url: string;
  readonly database: string;
  readonly username: string;
  readonly defaultUserId: number | undefined;
  readonly helpdesk: HelpdeskNamespace;
  readonly crm: CRMNamespace;
  readonly tasks: TaskNamespace;
  readonly projects: ProjectNamespace;
  readonly accountMoves: AccountMoveNamespace;
  readonly activities: ActivityNamespace;
  readonly documents: DocumentNamespace;
  readonly knowledge: KnowledgeNamespace;
  readonly timer: TimerNamespace;
  readonly security: SecurityNamespace;
  readonly generic: GenericNamespace;

  private readonly config: OdooConfig;
  private readonly protocol: OdooProtocol;
  private readonly fetchImplementation: FetchLike | undefined;
  private readonly sleepImplementation: Sleep | undefined;
  private transportValue: OdooTransportApi | null;
  private transportPromise: Promise<OdooTransportApi> | null = null;

  constructor(config: OdooConfig, options: OdooClientOptions = {}) {
    this.config = config;
    this.url = config.url.replace(/\/+$/u, "");
    this.database = config.database;
    this.username = config.username;
    this.defaultUserId = config.defaultUserId;
    this.protocol =
      options.protocol ?? (options.autoDetect === false ? "jsonrpc" : "auto");
    this.fetchImplementation = options.fetch;
    this.sleepImplementation = options.sleep;
    this.transportValue = options.transport ?? null;
    this.helpdesk = new HelpdeskNamespace(this);
    this.crm = new CRMNamespace(this);
    this.tasks = new TaskNamespace(this);
    this.projects = new ProjectNamespace(this);
    this.accountMoves = new AccountMoveNamespace(this);
    this.activities = new ActivityNamespace(this);
    this.documents = new DocumentNamespace(this);
    this.knowledge = new KnowledgeNamespace(this);
    this.timer = new TimerNamespace(this);
    this.security = new SecurityNamespace(this);
    this.generic = new GenericNamespace(this);
  }

  static fromBindings(
    bindings: OdooWorkerBindings,
    options: OdooWorkerClientOptions = {},
  ): OdooClient {
    const requiredBindings = [
      "ODOO_URL",
      "ODOO_DATABASE",
      "ODOO_USERNAME",
      "ODOO_PASSWORD",
    ] as const;
    for (const name of requiredBindings) {
      if (typeof bindings[name] !== "string" || bindings[name].length === 0) {
        throw new ConfigurationError(
          `Missing required Odoo Worker binding: ${name}`,
        );
      }
    }

    const config: OdooConfig = {
      url: bindings.ODOO_URL,
      database: bindings.ODOO_DATABASE,
      username: bindings.ODOO_USERNAME,
      password: bindings.ODOO_PASSWORD,
    };
    if (options.defaultUserId !== undefined)
      config.defaultUserId = options.defaultUserId;
    if (options.timeoutMs !== undefined) config.timeoutMs = options.timeoutMs;
    if (options.retry !== undefined) config.retry = options.retry;
    if (options.headers !== undefined) config.headers = options.headers;

    const clientOptions: OdooClientOptions = {
      protocol: options.protocol ?? "auto",
    };
    if (options.fetch !== undefined) clientOptions.fetch = options.fetch;
    if (options.sleep !== undefined) clientOptions.sleep = options.sleep;
    return new OdooClient(config, clientOptions);
  }

  get transport(): OdooTransportApi {
    if (this.transportValue === null) {
      throw new Error(
        "Transport not initialised. Call an async client method first.",
      );
    }
    return this.transportValue;
  }

  get isJson2(): boolean {
    return this.transportValue?.dialect === "json2";
  }

  async getUid(): Promise<number> {
    return (await this.ensureTransport()).getUid();
  }

  async execute(
    model: string,
    method: string,
    args: readonly unknown[] = [],
    kwargs?: Readonly<Record<string, unknown>>,
  ): Promise<unknown> {
    return (await this.ensureTransport()).executeKw(
      model,
      method,
      args,
      kwargs ?? null,
    );
  }

  /**
   * Inject `sudo_user_id` into the call context for server-side code that supports it.
   * This does not change the authenticated identity or access checks by itself.
   */
  executeWithUserContext(
    model: string,
    method: string,
    userId: number,
    args: readonly unknown[] = [],
    kwargs: Readonly<Record<string, unknown>> = {},
  ): Promise<unknown> {
    const context =
      typeof kwargs.context === "object" && kwargs.context !== null
        ? (kwargs.context as Readonly<Record<string, unknown>>)
        : {};
    return this.execute(model, method, args, {
      ...kwargs,
      context: { ...context, sudo_user_id: userId },
    });
  }

  async search(model: string, options: SearchOptions = {}): Promise<number[]> {
    return (await this.ensureTransport()).search(
      model,
      options.domain ?? null,
      options.limit ?? null,
      options.offset ?? 0,
      options.order ?? null,
    );
  }

  async read(
    model: string,
    ids: readonly number[],
    fields?: readonly string[],
  ): Promise<OdooRecord[]> {
    return normalizeFalse(
      await (await this.ensureTransport()).read(model, ids, fields ?? null),
    );
  }

  async searchRead(
    model: string,
    options: SearchReadOptions = {},
  ): Promise<OdooRecord[]> {
    return normalizeFalse(
      await (
        await this.ensureTransport()
      ).searchRead(
        model,
        options.domain ?? null,
        options.fields ?? null,
        options.limit ?? null,
        options.offset ?? 0,
        options.order ?? null,
      ),
    );
  }

  async create(
    model: string,
    values: Readonly<Record<string, unknown>>,
    context?: Readonly<Record<string, unknown>>,
  ): Promise<number> {
    return (await this.ensureTransport()).create(
      model,
      processContentValues(values),
      context ?? null,
    );
  }

  async write(
    model: string,
    ids: readonly number[],
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean> {
    return (await this.ensureTransport()).write(
      model,
      ids,
      processContentValues(values),
    );
  }

  async unlink(model: string, ids: readonly number[]): Promise<boolean> {
    return (await this.ensureTransport()).unlink(model, ids);
  }

  async fieldsGet(
    model: string,
    fields?: readonly string[],
    attributes?: readonly string[],
  ): Promise<Record<string, unknown>> {
    const kwargs: Record<string, unknown> = {};
    if (attributes !== undefined) kwargs.attributes = attributes;
    return (await this.execute(
      model,
      "fields_get",
      [fields ?? []],
      kwargs,
    )) as Record<string, unknown>;
  }

  async nameSearch(
    model: string,
    name: string,
    domain: Domain = [],
    limit = 7,
  ): Promise<NameSearchResult[]> {
    return (await this.ensureTransport()).nameSearch(
      model,
      name,
      domain,
      limit,
    );
  }

  async close(): Promise<void> {
    if (this.transportValue !== null) await this.transportValue.close();
  }

  private async ensureTransport(): Promise<OdooTransportApi> {
    if (this.transportValue !== null) return this.transportValue;
    if (this.transportPromise === null) {
      this.transportPromise = this.initializeTransport();
    }
    try {
      this.transportValue = await this.transportPromise;
      return this.transportValue;
    } finally {
      this.transportPromise = null;
    }
  }

  private transportOptions(): TransportOptions {
    const options: TransportOptions = {
      url: this.config.url,
      database: this.config.database,
      username: this.config.username,
      password: this.config.password,
    };
    if (this.config.timeoutMs !== undefined)
      options.timeoutMs = this.config.timeoutMs;
    if (this.config.retry !== undefined) options.retry = this.config.retry;
    if (this.config.headers !== undefined)
      options.headers = this.config.headers;
    if (this.fetchImplementation !== undefined)
      options.fetch = this.fetchImplementation;
    if (this.sleepImplementation !== undefined)
      options.sleep = this.sleepImplementation;
    return options;
  }

  private async initializeTransport(): Promise<OdooTransportApi> {
    const options = this.transportOptions();
    if (this.protocol === "jsonrpc") return new LegacyTransport(options);
    const json2 = new JSON2Transport(options);
    if (this.protocol === "json2") return json2;
    try {
      await json2.authenticate();
      return json2;
    } catch (error) {
      if (!(error instanceof VodooError)) throw error;
      await json2.close();
      return new LegacyTransport(options);
    }
  }
}
