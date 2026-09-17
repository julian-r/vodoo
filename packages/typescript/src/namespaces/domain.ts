import type { OdooClientApi, SearchReadOptions } from "../client-api.js";
import { RecordNotFoundError } from "../errors.js";
import type { OdooRecord } from "../types.js";

export interface NamespaceMetadata {
  readonly model: string;
  readonly defaultFields: readonly string[];
  readonly defaultDetailFields?: readonly string[];
}

export interface ListOptions extends Omit<SearchReadOptions, "fields"> {
  fields?: readonly string[];
}

/** Initial shared namespace slice: list/get/set/fields/url only. */
export class DomainNamespace {
  protected readonly client: OdooClientApi;
  protected readonly metadata: NamespaceMetadata;

  constructor(client: OdooClientApi, metadata: NamespaceMetadata) {
    this.client = client;
    this.metadata = metadata;
  }

  protected decodeRecord(record: OdooRecord): OdooRecord {
    return record;
  }

  async list(options: ListOptions = {}): Promise<OdooRecord[]> {
    const request: SearchReadOptions = {
      fields: options.fields ?? this.metadata.defaultFields,
      limit: options.limit === undefined ? 50 : options.limit,
      order: options.order ?? "create_date desc",
    };
    if (options.domain !== undefined) request.domain = options.domain;
    if (options.offset !== undefined) request.offset = options.offset;
    const records = await this.client.searchRead(this.metadata.model, request);
    return records.map((record) => this.decodeRecord(record));
  }

  async get(recordId: number, fields?: readonly string[]): Promise<OdooRecord> {
    const selectedFields = fields ?? this.metadata.defaultDetailFields;
    const records = await this.client.read(
      this.metadata.model,
      [recordId],
      selectedFields,
    );
    const record = records[0];
    if (record === undefined) {
      throw new RecordNotFoundError(this.metadata.model, recordId);
    }
    return this.decodeRecord(record);
  }

  set(
    recordId: number,
    values: Readonly<Record<string, unknown>>,
  ): Promise<boolean> {
    return this.client.write(this.metadata.model, [recordId], values);
  }

  fields(): Promise<Record<string, unknown>> {
    return this.client.fieldsGet(this.metadata.model);
  }

  url(recordId: number): string {
    return `${this.client.url.replace(/\/+$/u, "")}/web#id=${recordId}&model=${this.metadata.model}&view_type=form`;
  }
}
