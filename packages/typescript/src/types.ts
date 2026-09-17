export type JsonPrimitive = boolean | number | string | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export interface JsonObject {
  [key: string]: JsonValue;
}

/** Dynamic Odoo record. Generic client calls preserve wire field names and values. */
export type OdooRecord = Record<string, unknown>;
export type DomainTerm = readonly [
  field: string,
  operator: string,
  value: unknown,
];
export type Domain = ReadonlyArray<DomainTerm | "&" | "|" | "!">;
export type NameSearchResult = readonly [id: number, displayName: string];

export interface RetryConfig {
  maxRetries: number;
  backoffBaseMs: number;
  backoffMaxMs: number;
}

export const DEFAULT_RETRY: Readonly<RetryConfig> = Object.freeze({
  maxRetries: 2,
  backoffBaseMs: 500,
  backoffMaxMs: 30_000,
});

export interface OdooConfig {
  url: string;
  database: string;
  username: string;
  password: string;
  defaultUserId?: number;
  timeoutMs?: number;
  retry?: Partial<RetryConfig>;
  headers?: Readonly<Record<string, string>>;
}

export interface SearchOptions {
  domain?: Domain;
  limit?: number | null;
  offset?: number;
  order?: string;
}

export interface SearchReadOptions extends SearchOptions {
  fields?: readonly string[];
}

export type FetchLike = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;
export type Sleep = (milliseconds: number) => Promise<void>;
