import type {
  OdooClientApi,
  SearchOptions,
  SearchReadOptions,
} from "./client-api.js";
import { VodooError } from "./errors.js";
import { ProjectNamespace } from "./namespaces/projects.js";
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
  Sleep,
} from "./types.js";

export interface OdooClientOptions {
  transport?: OdooTransportApi;
  autoDetect?: boolean;
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
  readonly projects: ProjectNamespace;

  private readonly config: OdooConfig;
  private readonly autoDetect: boolean;
  private readonly fetchImplementation: FetchLike | undefined;
  private readonly sleepImplementation: Sleep | undefined;
  private transportValue: OdooTransportApi | null;
  private transportPromise: Promise<OdooTransportApi> | null = null;

  constructor(config: OdooConfig, options: OdooClientOptions = {}) {
    this.config = config;
    this.url = config.url.replace(/\/+$/u, "");
    this.database = config.database;
    this.username = config.username;
    this.autoDetect = options.autoDetect ?? true;
    this.fetchImplementation = options.fetch;
    this.sleepImplementation = options.sleep;
    this.transportValue = options.transport ?? null;
    this.projects = new ProjectNamespace(this);
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
      values,
      context ?? null,
    );
  }

  async write(
    model: string,
    ids: readonly number[],
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean> {
    return (await this.ensureTransport()).write(model, ids, values);
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
    if (!this.autoDetect) return new LegacyTransport(options);
    const json2 = new JSON2Transport(options);
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
