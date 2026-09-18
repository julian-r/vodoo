import type { OdooClientApi, SearchReadOptions } from "../client-api.js";
import { binaryBytes, decodeBase64, encodeBase64 } from "../binary.js";
import type { BinaryInput } from "../binary.js";
import { richTextToHtml } from "../content.js";
import type { RichText } from "../content.js";
import { decodeRecordDates } from "../dates.js";
import {
  ConfigurationError,
  RecordNotFoundError,
  VodooError,
} from "../errors.js";
import type { OdooRecord } from "../types.js";

const TAG_FIELDS = ["id", "name", "color"] as const;
const MESSAGE_FIELDS = [
  "id",
  "date",
  "author_id",
  "body",
  "subject",
  "message_type",
  "subtype_id",
  "email_from",
] as const;
const ATTACHMENT_LIST_FIELDS = [
  "id",
  "name",
  "file_size",
  "mimetype",
  "create_date",
] as const;
const ATTACHMENT_READ_FIELDS = ["name", "datas", "file_size"] as const;

export interface NamespaceMetadata {
  readonly model: string;
  readonly defaultFields: readonly string[];
  readonly defaultDetailFields?: readonly string[];
  readonly tagModel?: string;
}

export interface ListOptions extends Omit<SearchReadOptions, "fields"> {
  fields?: readonly string[];
}

export interface MessageOptions {
  userId?: number;
  markdown?: boolean;
}

export interface AttachmentOptions {
  mimetype?: string;
}

export interface AttachmentData {
  readonly id: number;
  readonly name: string;
  readonly data: Uint8Array;
  readonly mimetype?: string;
}

function many2OneId(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
}

/** Shared namespace CRUD, messaging, tags, and in-memory attachments. */
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

  comment(
    recordId: number,
    message: RichText,
    options: MessageOptions = {},
  ): Promise<boolean> {
    return this.commentWithId(recordId, message, options).then(
      (messageId) => messageId > 0,
    );
  }

  commentWithId(
    recordId: number,
    message: RichText,
    options: MessageOptions = {},
  ): Promise<number> {
    return this.postMessage(recordId, message, false, options);
  }

  note(
    recordId: number,
    message: RichText,
    options: MessageOptions = {},
  ): Promise<boolean> {
    return this.noteWithId(recordId, message, options).then(
      (messageId) => messageId > 0,
    );
  }

  noteWithId(
    recordId: number,
    message: RichText,
    options: MessageOptions = {},
  ): Promise<number> {
    return this.postMessage(recordId, message, true, options);
  }

  async messages(
    recordId: number,
    limit: number | null = null,
  ): Promise<OdooRecord[]> {
    const records = await this.client.searchRead("mail.message", {
      domain: [
        ["model", "=", this.metadata.model],
        ["res_id", "=", recordId],
      ],
      fields: MESSAGE_FIELDS,
      order: "date desc",
      limit,
    });
    return records.map((record) =>
      decodeRecordDates(record, { date: "datetime" }),
    );
  }

  async tags(): Promise<OdooRecord[]> {
    if (this.metadata.tagModel === undefined) {
      throw new VodooError(`No tag model defined for ${this.metadata.model}`);
    }
    return this.client.searchRead(this.metadata.tagModel, {
      fields: TAG_FIELDS,
      order: "name",
    });
  }

  async addTag(recordId: number, tagId: number): Promise<boolean> {
    const record = await this.get(recordId, ["tag_ids"]);
    const existing = Array.isArray(record.tag_ids)
      ? record.tag_ids.filter(
          (value): value is number => typeof value === "number",
        )
      : [];
    if (existing.includes(tagId)) return true;
    return this.client.write(this.metadata.model, [recordId], {
      tag_ids: [[6, 0, [...existing, tagId]]],
    });
  }

  async attachments(recordId: number): Promise<OdooRecord[]> {
    const records = await this.client.searchRead("ir.attachment", {
      domain: [
        ["res_model", "=", this.metadata.model],
        ["res_id", "=", recordId],
      ],
      fields: ATTACHMENT_LIST_FIELDS,
    });
    return records.map((record) =>
      decodeRecordDates(record, { create_date: "datetime" }),
    );
  }

  /** Attach Worker-safe binary data. Filesystem paths are intentionally unsupported. */
  async attach(
    recordId: number,
    data: BinaryInput,
    name: string,
    options: AttachmentOptions = {},
  ): Promise<number> {
    const bytes = await binaryBytes(data);
    const values: Record<string, unknown> = {
      name,
      datas: encodeBase64(bytes),
      res_model: this.metadata.model,
      res_id: recordId,
      type: "binary",
    };
    const mimetype =
      options.mimetype ??
      (typeof Blob !== "undefined" && data instanceof Blob && data.type !== ""
        ? data.type
        : undefined);
    if (mimetype !== undefined) values.mimetype = mimetype;
    return this.client.create("ir.attachment", values);
  }

  async attachmentData(attachmentId: number): Promise<Uint8Array> {
    const attachments = await this.client.read(
      "ir.attachment",
      [attachmentId],
      ATTACHMENT_READ_FIELDS,
    );
    const attachment = attachments[0];
    if (attachment === undefined) {
      throw new RecordNotFoundError("ir.attachment", attachmentId);
    }
    if (typeof attachment.datas === "string") {
      return decodeBase64(attachment.datas);
    }
    if (attachment.file_size === 0) return new Uint8Array();
    throw new RecordNotFoundError("ir.attachment", attachmentId);
  }

  async allAttachmentData(recordId: number): Promise<AttachmentData[]> {
    const metadata = await this.attachments(recordId);
    const result: AttachmentData[] = [];
    for (const attachment of metadata) {
      if (typeof attachment.id !== "number") continue;
      try {
        const records = await this.client.read(
          "ir.attachment",
          [attachment.id],
          ["id", ...ATTACHMENT_READ_FIELDS],
        );
        const record = records[0];
        if (record === undefined) continue;
        let data: Uint8Array;
        if (typeof record.datas === "string") {
          data = decodeBase64(record.datas);
        } else if (record.file_size === 0) {
          data = new Uint8Array();
        } else {
          continue;
        }
        const item: AttachmentData = {
          id: attachment.id,
          name:
            typeof record.name === "string"
              ? record.name
              : `attachment_${attachment.id}`,
          data,
        };
        if (typeof attachment.mimetype === "string") {
          result.push({ ...item, mimetype: attachment.mimetype });
        } else {
          result.push(item);
        }
      } catch {
        // Match Python all_attachment_data: one unreadable attachment is skipped.
      }
    }
    return result;
  }

  /** Worker-safe replacement for filesystem download: return matching bytes in memory. */
  async downloadAttachments(
    recordId: number,
    extension?: string,
  ): Promise<AttachmentData[]> {
    const attachments = await this.allAttachmentData(recordId);
    if (extension === undefined) return attachments;
    const suffix = `.${extension.replace(/^\./u, "").toLocaleLowerCase("und")}`;
    return attachments.filter((attachment) =>
      attachment.name.toLocaleLowerCase("und").endsWith(suffix),
    );
  }

  /** Python-compatible name for the in-memory Worker download adaptation. */
  download(recordId: number, extension?: string): Promise<AttachmentData[]> {
    return this.downloadAttachments(recordId, extension);
  }

  url(recordId: number): string {
    return `${this.client.url.replace(/\/+$/u, "")}/web#id=${recordId}&model=${this.metadata.model}&view_type=form`;
  }

  private async postMessage(
    recordId: number,
    message: RichText,
    isNote: boolean,
    options: MessageOptions,
  ): Promise<number> {
    const userId = options.userId ?? this.client.defaultUserId;
    if (userId === undefined) {
      throw new ConfigurationError("No default user ID configured");
    }
    const users = await this.client.read("res.users", [userId], ["partner_id"]);
    if (users[0] === undefined) {
      throw new RecordNotFoundError("res.users", userId);
    }
    const partnerId = many2OneId(users[0].partner_id);
    if (partnerId === null) {
      throw new RecordNotFoundError("res.partner", 0);
    }
    const subtypeIds = await this.client.search("mail.message.subtype", {
      domain: [["name", "=", isNote ? "Note" : "Discussions"]],
      limit: 1,
    });
    return this.client.create("mail.message", {
      model: this.metadata.model,
      res_id: recordId,
      body: richTextToHtml(message, options.markdown ?? true),
      message_type: isNote ? "notification" : "comment",
      subtype_id: subtypeIds[0] ?? false,
      author_id: partnerId,
    });
  }
}
