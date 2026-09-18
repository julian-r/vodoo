import type { OdooClientApi } from "../client-api.js";
import { richTextToHtml } from "../content.js";
import type { RichText } from "../content.js";
import { GeneratedKnowledgeNamespace } from "../generated/knowledge.js";
import type { OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

export interface KnowledgeRecord extends OdooRecord {
  id: number;
  name: string;
  write_date?: Date | null;
}

export interface CreateArticleOptions {
  body?: RichText;
  parentId?: number;
  category?: string;
  icon?: string;
  extraFields?: Readonly<Record<string, unknown>>;
}

export class KnowledgeNamespace extends GeneratedKnowledgeNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<KnowledgeRecord[]> {
    return (await super.list(options)) as KnowledgeRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<KnowledgeRecord> {
    return (await super.get(recordId, fields)) as KnowledgeRecord;
  }

  create(name: string, options: CreateArticleOptions = {}): Promise<number> {
    const values: Record<string, unknown> = {
      name,
      ...options.extraFields,
    };
    if (options.body !== undefined) {
      values.body = richTextToHtml(options.body);
    }
    if (options.parentId !== undefined) values.parent_id = options.parentId;
    if (options.category !== undefined) values.category = options.category;
    if (options.icon !== undefined) values.icon = options.icon;
    return this.client.create("knowledge.article", values);
  }

  /** Async TypeScript adaptation of Python's article_url lookup. */
  async resolveUrl(recordId: number): Promise<string> {
    const article = await this.get(recordId, ["article_url"]);
    return typeof article.article_url === "string" && article.article_url !== ""
      ? article.article_url
      : this.url(recordId);
  }
}
