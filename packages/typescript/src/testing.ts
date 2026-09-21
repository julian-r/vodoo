import type {
  OdooClientApi,
  SearchOptions,
  SearchReadOptions,
} from "./client-api.js";
import type { Domain, NameSearchResult, OdooRecord } from "./types.js";

export interface RecordedCall {
  readonly method: string;
  readonly args: readonly unknown[];
}

/** Minimal queue-backed client for generated namespace conformance tests. */
export class RecordingClient implements OdooClientApi {
  readonly calls: RecordedCall[] = [];
  readonly username = "user@example.com";
  readonly defaultUserId: number | undefined;

  constructor(
    readonly url = "https://odoo.example.com",
    private readonly responses: unknown[] = [],
    defaultUserId?: number,
    readonly isJson2 = false,
  ) {
    this.defaultUserId = defaultUserId;
  }

  private next(method: string, args: readonly unknown[]): unknown {
    this.calls.push({ method, args });
    if (this.responses.length === 0)
      throw new Error(`No response queued for ${method}`);
    const response = this.responses.shift();
    if (response instanceof Error) throw response;
    return response;
  }

  async getUid(): Promise<number> {
    return this.next("getUid", []) as number;
  }

  async execute(
    model: string,
    method: string,
    args: readonly unknown[] = [],
    kwargs?: Readonly<Record<string, unknown>>,
  ): Promise<unknown> {
    return this.next("execute", [model, method, args, kwargs]);
  }

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

  async search(model: string, options?: SearchOptions): Promise<number[]> {
    return this.next("search", [model, options]) as number[];
  }

  async read(
    model: string,
    ids: readonly number[],
    fields?: readonly string[],
  ): Promise<OdooRecord[]> {
    return this.next("read", [model, ids, fields]) as OdooRecord[];
  }

  async searchRead(
    model: string,
    options?: SearchReadOptions,
  ): Promise<OdooRecord[]> {
    return this.next("searchRead", [model, options]) as OdooRecord[];
  }

  async create(
    model: string,
    values: Readonly<Record<string, unknown>>,
    context?: Readonly<Record<string, unknown>>,
  ): Promise<number> {
    return this.next("create", [model, values, context]) as number;
  }

  async write(
    model: string,
    ids: readonly number[],
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean> {
    return this.next("write", [model, ids, values]) as boolean;
  }

  async unlink(model: string, ids: readonly number[]): Promise<boolean> {
    return this.next("unlink", [model, ids]) as boolean;
  }

  async fieldsGet(
    model: string,
    fields?: readonly string[],
    attributes?: readonly string[],
  ): Promise<Record<string, unknown>> {
    return this.next("fieldsGet", [model, fields, attributes]) as Record<
      string,
      unknown
    >;
  }

  async nameSearch(
    model: string,
    name: string,
    domain?: Domain,
    limit?: number,
  ): Promise<NameSearchResult[]> {
    return this.next("nameSearch", [
      model,
      name,
      domain,
      limit,
    ]) as NameSearchResult[];
  }
}
