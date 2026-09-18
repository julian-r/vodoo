import {
  AuthenticationError,
  HttpStatusError,
  NetworkError,
  TransportError,
  transportErrorFromData,
} from "./errors.js";
import type {
  Domain,
  FetchLike,
  JsonObject,
  NameSearchResult,
  OdooRecord,
  RetryConfig,
  Sleep,
} from "./types.js";
import { DEFAULT_RETRY } from "./types.js";

const RETRYABLE_METHODS = new Set([
  "search",
  "search_read",
  "read",
  "fields_get",
  "name_search",
]);

export interface TransportOptions {
  url: string;
  database: string;
  username: string;
  password: string;
  timeoutMs?: number;
  retry?: Partial<RetryConfig>;
  headers?: Readonly<Record<string, string>>;
  fetch?: FetchLike;
  sleep?: Sleep;
}

export interface OdooTransportApi {
  readonly dialect: "jsonrpc" | "json2";
  getUid(): Promise<number>;
  authenticate(): Promise<number>;
  executeKw(
    model: string,
    method: string,
    args: readonly unknown[],
    kwargs?: Readonly<Record<string, unknown>> | null,
  ): Promise<unknown>;
  searchRead(
    model: string,
    domain?: Domain | null,
    fields?: readonly string[] | null,
    limit?: number | null,
    offset?: number,
    order?: string | null,
  ): Promise<OdooRecord[]>;
  search(
    model: string,
    domain?: Domain | null,
    limit?: number | null,
    offset?: number,
    order?: string | null,
  ): Promise<number[]>;
  read(
    model: string,
    ids: readonly number[],
    fields?: readonly string[] | null,
  ): Promise<OdooRecord[]>;
  create(
    model: string,
    values: Readonly<Record<string, unknown>>,
    context?: Readonly<Record<string, unknown>> | null,
  ): Promise<number>;
  write(
    model: string,
    ids: readonly number[],
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean>;
  unlink(model: string, ids: readonly number[]): Promise<boolean>;
  nameSearch(
    model: string,
    name: string,
    domain?: Domain | null,
    limit?: number,
  ): Promise<NameSearchResult[]>;
  close(): Promise<void>;
}

interface ResponseBody {
  response: Response;
  text: string;
}

const defaultSleep: Sleep = (milliseconds) =>
  new Promise((resolve) => globalThis.setTimeout(resolve, milliseconds));

function normalizeUrl(url: string): string {
  return url.replace(/\/+$/u, "");
}

function asJsonObject(value: unknown): JsonObject | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as JsonObject;
}

function parseJson(text: string): unknown {
  return JSON.parse(text) as unknown;
}

export abstract class OdooTransport implements OdooTransportApi {
  abstract readonly dialect: "jsonrpc" | "json2";

  readonly url: string;
  readonly database: string;
  readonly username: string;
  readonly password: string;
  readonly timeoutMs: number;
  readonly retry: Readonly<RetryConfig>;

  protected uid: number | null = null;
  protected readonly extraHeaders: Readonly<Record<string, string>>;
  private readonly fetchImplementation: FetchLike;
  private readonly sleepImplementation: Sleep;

  constructor(options: TransportOptions) {
    this.url = normalizeUrl(options.url);
    this.database = options.database.trim();
    this.username = options.username.trim();
    // Passwords and API keys are opaque credentials; whitespace may be significant.
    this.password = options.password;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.retry = Object.freeze({ ...DEFAULT_RETRY, ...options.retry });
    this.extraHeaders = options.headers ?? {};
    this.fetchImplementation =
      options.fetch ?? globalThis.fetch.bind(globalThis);
    this.sleepImplementation = options.sleep ?? defaultSleep;
  }

  async getUid(): Promise<number> {
    if (this.uid === null) {
      this.uid = await this.authenticate();
    }
    return this.uid;
  }

  abstract authenticate(): Promise<number>;

  abstract executeKw(
    model: string,
    method: string,
    args: readonly unknown[],
    kwargs?: Readonly<Record<string, unknown>> | null,
  ): Promise<unknown>;

  async close(): Promise<void> {
    // fetch has no client lifecycle to close.
  }

  async searchRead(
    model: string,
    domain: Domain | null = null,
    fields: readonly string[] | null = null,
    limit: number | null = null,
    offset = 0,
    order: string | null = null,
  ): Promise<OdooRecord[]> {
    const kwargs: Record<string, unknown> = {};
    if (fields !== null) kwargs.fields = fields;
    if (limit !== null) kwargs.limit = limit;
    if (offset > 0) kwargs.offset = offset;
    if (order !== null) kwargs.order = order;
    return (await this.executeKw(
      model,
      "search_read",
      [domain ?? []],
      kwargs,
    )) as OdooRecord[];
  }

  async search(
    model: string,
    domain: Domain | null = null,
    limit: number | null = null,
    offset = 0,
    order: string | null = null,
  ): Promise<number[]> {
    const kwargs: Record<string, unknown> = {};
    if (limit !== null) kwargs.limit = limit;
    if (offset > 0) kwargs.offset = offset;
    if (order !== null) kwargs.order = order;
    return (await this.executeKw(
      model,
      "search",
      [domain ?? []],
      kwargs,
    )) as number[];
  }

  async read(
    model: string,
    ids: readonly number[],
    fields: readonly string[] | null = null,
  ): Promise<OdooRecord[]> {
    const args: unknown[] = [ids];
    if (fields !== null) args.push(fields);
    return (await this.executeKw(model, "read", args)) as OdooRecord[];
  }

  async create(
    model: string,
    values: Readonly<Record<string, unknown>>,
    context: Readonly<Record<string, unknown>> | null = null,
  ): Promise<number> {
    const kwargs = context === null ? null : { context };
    const result = await this.executeKw(model, "create", [values], kwargs);
    const value =
      Array.isArray(result) && result.length === 1 ? result[0] : result;
    return Number(value);
  }

  async write(
    model: string,
    ids: readonly number[],
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean> {
    return (await this.executeKw(model, "write", [ids, values])) as boolean;
  }

  async unlink(model: string, ids: readonly number[]): Promise<boolean> {
    return (await this.executeKw(model, "unlink", [ids])) as boolean;
  }

  async nameSearch(
    model: string,
    name: string,
    domain: Domain | null = null,
    limit = 7,
  ): Promise<NameSearchResult[]> {
    const result = await this.executeKw(model, "name_search", [], {
      name,
      args: domain ?? [],
      limit,
    });
    return parseNameSearch(result);
  }

  protected async withRetry<T>(
    method: string,
    operation: () => Promise<T>,
  ): Promise<T> {
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.retry.maxRetries; attempt += 1) {
      try {
        return await operation();
      } catch (error) {
        lastError = error;
        const shouldRetry =
          attempt < this.retry.maxRetries &&
          RETRYABLE_METHODS.has(method) &&
          error instanceof NetworkError;
        if (!shouldRetry) throw error;
        await this.sleepImplementation(
          Math.min(
            this.retry.backoffBaseMs * 2 ** attempt,
            this.retry.backoffMaxMs,
          ),
        );
      }
    }
    throw lastError;
  }

  protected async request(
    url: string,
    init: RequestInit,
  ): Promise<ResponseBody> {
    const controller = new AbortController();
    const timer = globalThis.setTimeout(
      () => controller.abort(),
      this.timeoutMs,
    );
    try {
      const response = await this.fetchImplementation(url, {
        ...init,
        signal: controller.signal,
      });
      let text: string;
      try {
        text = await response.text();
      } catch (error) {
        throw new NetworkError("Failed to read Odoo response", {
          cause: error,
        });
      }
      return { response, text };
    } catch (error) {
      if (error instanceof NetworkError) throw error;
      const message = controller.signal.aborted
        ? "Odoo request timed out"
        : "Odoo network error";
      throw new NetworkError(message, { cause: error });
    } finally {
      globalThis.clearTimeout(timer);
    }
  }
}

export class LegacyTransport extends OdooTransport {
  readonly dialect = "jsonrpc" as const;

  async authenticate(): Promise<number> {
    if (this.uid !== null) return this.uid;
    const result = await this.callService("common", "authenticate", [
      this.database,
      this.username,
      this.password,
      {},
    ]);
    if (typeof result !== "number" || result <= 0) {
      throw new AuthenticationError("Authentication failed");
    }
    this.uid = result;
    return result;
  }

  async executeKw(
    model: string,
    method: string,
    args: readonly unknown[],
    kwargs: Readonly<Record<string, unknown>> | null = null,
  ): Promise<unknown> {
    const uid = await this.getUid();
    const callArgs = [
      this.database,
      uid,
      this.password,
      model,
      method,
      args,
      kwargs ?? {},
    ];
    return this.withRetry(method, () =>
      this.callService("object", "execute_kw", callArgs),
    );
  }

  async callService(
    service: string,
    method: string,
    args: readonly unknown[],
  ): Promise<unknown> {
    const headers = new Headers(this.extraHeaders);
    headers.set("Content-Type", "application/json");
    const { response, text } = await this.request(`${this.url}/jsonrpc`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        jsonrpc: "2.0",
        method: "call",
        params: { service, method, args },
        id: null,
      }),
    });
    if (!response.ok) {
      throw new HttpStatusError(response.status, response.statusText);
    }
    const payload = asJsonObject(parseJson(text));
    if (payload === null) return undefined;
    const error = asJsonObject(payload.error);
    if (error !== null) {
      const data = asJsonObject(error.data);
      const code = typeof error.code === "number" ? error.code : -1;
      const fallback =
        typeof error.message === "string" ? error.message : "Unknown error";
      const message =
        typeof data?.message === "string" ? data.message : fallback;
      throw transportErrorFromData(message, code, data);
    }
    return payload.result;
  }
}

export class JSON2Transport extends OdooTransport {
  readonly dialect = "json2" as const;

  async authenticate(): Promise<number> {
    if (this.uid !== null) return this.uid;
    let records: OdooRecord[];
    try {
      records = await this.searchRead(
        "res.users",
        [["login", "=", this.username]],
        ["id"],
        1,
      );
    } catch (error) {
      if (error instanceof TransportError) {
        throw new AuthenticationError(
          `Authentication failed — API key may be invalid or lacks access: ${error.message}`,
          { cause: error },
        );
      }
      throw error;
    }
    const uid = records[0]?.id;
    if (records.length === 0) {
      throw new AuthenticationError(
        `Authentication failed — user '${this.username}' not found. If using an API key, ensure it belongs to this user.`,
      );
    }
    if (typeof uid !== "number" || !Number.isInteger(uid)) {
      throw new AuthenticationError("Authentication failed — invalid user ID");
    }
    this.uid = uid;
    return uid;
  }

  async executeKw(
    model: string,
    method: string,
    args: readonly unknown[],
    kwargs: Readonly<Record<string, unknown>> | null = null,
  ): Promise<unknown> {
    const body = buildJSON2Body(method, args, kwargs);
    return this.withRetry(method, () => this.sendRequest(model, method, body));
  }

  private async sendRequest(
    model: string,
    method: string,
    body: Readonly<Record<string, unknown>>,
  ): Promise<unknown> {
    const headers = new Headers(this.extraHeaders);
    headers.set("Content-Type", "application/json; charset=utf-8");
    headers.set("Authorization", `bearer ${this.password}`);
    headers.set("User-Agent", "Vodoo");
    if (this.database) headers.set("X-Odoo-Database", this.database);
    const { response, text } = await this.request(
      `${this.url}/json/2/${model}/${method}`,
      {
        method: "POST",
        headers,
        body: JSON.stringify(body),
      },
    );
    if (!response.ok) {
      let parsed: JsonObject | null = null;
      try {
        parsed = asJsonObject(parseJson(text));
      } catch {
        // Python falls back to the status-only message for an invalid error body.
      }
      const message =
        typeof parsed?.message === "string"
          ? parsed.message
          : `HTTP ${response.status}`;
      const nestedData = asJsonObject(parsed?.data);
      const data =
        nestedData !== null && Object.keys(nestedData).length > 0
          ? nestedData
          : parsed;
      throw transportErrorFromData(message, response.status, data);
    }
    return parseJSON2Response(text);
  }
}

export function buildJSON2Body(
  method: string,
  args: readonly unknown[],
  kwargs: Readonly<Record<string, unknown>> | null = null,
): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  if (method === "search_read" || method === "search") {
    if (args.length > 0) body.domain = args[0];
  } else if (method === "read") {
    if (args.length > 0) body.ids = args[0];
    if (args.length > 1) body.fields = args[1];
  } else if (method === "create") {
    if (args.length > 0)
      body.vals_list = Array.isArray(args[0]) ? args[0] : [args[0]];
  } else if (method === "write") {
    if (args.length > 0) body.ids = args[0];
    if (args.length > 1) body.vals = args[1];
  } else if (method === "unlink") {
    if (args.length > 0) body.ids = args[0];
  } else if (method === "fields_get") {
    if (args.length > 0) body.allfields = args[0];
  } else if (
    args.length === 1 &&
    Array.isArray(args[0]) &&
    args[0].every(
      (item: unknown) => typeof item === "number" && Number.isInteger(item),
    )
  ) {
    body.ids = args[0];
  } else if (args.length > 0) {
    throw new TypeError(
      `JSON-2 method ${method} requires named keyword arguments; unsupported positional arguments were provided`,
    );
  }
  if (kwargs !== null) {
    Object.assign(body, kwargs);
    if ("args" in body) {
      body.domain = body.args;
      delete body.args;
    }
  }
  return body;
}

export function parseJSON2Response(text: string): unknown {
  const raw = text.trim();
  if (raw === "" || raw === "null" || raw === "false") return null;
  if (raw === "true") return true;
  try {
    return parseJson(raw);
  } catch {
    const number = Number(raw);
    if (raw !== "" && Number.isFinite(number)) return number;
    return raw;
  }
}

export function parseNameSearch(result: unknown): NameSearchResult[] {
  if (!Array.isArray(result)) return [];
  const pairs: NameSearchResult[] = [];
  for (const item of result) {
    if (
      Array.isArray(item) &&
      item.length >= 2 &&
      typeof item[0] === "number" &&
      Number.isInteger(item[0]) &&
      typeof item[1] === "string"
    ) {
      pairs.push([item[0], item[1]]);
    }
  }
  return pairs;
}
