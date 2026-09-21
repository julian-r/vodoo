import type { Domain, NameSearchResult, OdooRecord } from "./types.js";

export interface SearchOptions {
  domain?: Domain;
  limit?: number | null;
  offset?: number;
  order?: string;
}

export interface SearchReadOptions extends SearchOptions {
  fields?: readonly string[];
}

export interface OdooClientApi {
  readonly url: string;
  readonly username: string;
  readonly defaultUserId: number | undefined;
  readonly isJson2: boolean;
  getUid(): Promise<number>;
  execute(
    model: string,
    method: string,
    args?: readonly unknown[],
    kwargs?: Readonly<Record<string, unknown>>,
  ): Promise<unknown>;
  /**
   * Inject `sudo_user_id` into the call context.
   * This requires server-side support and does not change authentication or access checks itself.
   */
  executeWithUserContext(
    model: string,
    method: string,
    userId: number,
    args?: readonly unknown[],
    kwargs?: Readonly<Record<string, unknown>>,
  ): Promise<unknown>;
  search(model: string, options?: SearchOptions): Promise<number[]>;
  read(
    model: string,
    ids: readonly number[],
    fields?: readonly string[],
  ): Promise<OdooRecord[]>;
  searchRead(model: string, options?: SearchReadOptions): Promise<OdooRecord[]>;
  create(
    model: string,
    values: Readonly<Record<string, unknown>>,
    context?: Readonly<Record<string, unknown>>,
  ): Promise<number>;
  write(
    model: string,
    ids: readonly number[],
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean>;
  unlink(model: string, ids: readonly number[]): Promise<boolean>;
  fieldsGet(
    model: string,
    fields?: readonly string[],
    attributes?: readonly string[],
  ): Promise<Record<string, unknown>>;
  nameSearch(
    model: string,
    name: string,
    domain?: Domain,
    limit?: number,
  ): Promise<NameSearchResult[]>;
}
