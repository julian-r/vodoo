import { binaryBytes, decodeBase64, encodeBase64 } from "../binary.js";
import type { BinaryInput } from "../binary.js";
import type { OdooClientApi } from "../client-api.js";
import { Cmd } from "../commands.js";
import { RecordNotFoundError, VodooError } from "../errors.js";
import { GeneratedDocumentNamespace } from "../generated/documents.js";
import type { Domain, OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

const LEGACY_FOLDER_FIELDS = ["id", "name", "parent_folder_id"] as const;
const MODERN_FOLDER_FIELDS = ["id", "name", "folder_id"] as const;
const WINDOWS_RESERVED_NAMES = new Set([
  "CON",
  "PRN",
  "AUX",
  "NUL",
  ...Array.from({ length: 9 }, (_, index) => `COM${index + 1}`),
  ...Array.from({ length: 9 }, (_, index) => `LPT${index + 1}`),
]);

export interface DocumentRecord extends OdooRecord {
  id: number;
  name: string;
  create_date?: Date | null;
}

export interface DocumentFolder extends OdooRecord {
  id: number;
  name: string;
  parent_folder_id?: unknown;
  depth?: number;
  path?: string;
}

export interface FolderListOptions {
  limit?: number | null;
  tree?: boolean;
}

export interface DocumentUploadOptions {
  folder?: number | string;
  folderId?: number;
  tags?: readonly (number | string)[];
  owner?: number | string;
  mimetype?: string;
}

export interface DownloadedDocument {
  id: number;
  name: string;
  data: Uint8Array;
  mimetype?: string;
}

function selectionIncludesFolder(fields: Record<string, unknown>): boolean {
  const type = fields.type;
  if (typeof type !== "object" || type === null) return false;
  const selection = (type as Record<string, unknown>).selection;
  if (
    typeof selection === "object" &&
    selection !== null &&
    !Array.isArray(selection)
  ) {
    return Object.hasOwn(selection, "folder");
  }
  return (
    Array.isArray(selection) &&
    selection.some(
      (option) =>
        Array.isArray(option) && option.length > 0 && option[0] === "folder",
    )
  );
}

function relationId(value: unknown): number | null {
  if (typeof value === "number" && Number.isInteger(value)) return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
}

function numericId(value: number | string): number | null {
  const text = typeof value === "string" ? value.trim() : "";
  const parsed =
    typeof value === "number"
      ? value
      : /^[+-]?\d+$/u.test(text)
        ? Number(text)
        : null;
  if (parsed === null) return null;
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new VodooError("Record IDs must be positive integers");
  }
  return parsed;
}

function requireUniqueId(
  records: readonly OdooRecord[],
  model: string,
  value: string,
): number {
  if (records.length === 0) {
    throw new VodooError(`No ${model} record found matching '${value}'`);
  }
  if (records.length > 1) {
    throw new VodooError(
      `Multiple ${model} records match '${value}'; use a numeric ID`,
    );
  }
  const recordId = records[0]?.id;
  if (typeof recordId !== "number") {
    throw new VodooError(
      `${model} record matching '${value}' has no numeric ID`,
    );
  }
  return recordId;
}

function folderDomain(modern: boolean, name?: string): Domain {
  const domain: Array<Domain[number]> = modern ? [["type", "=", "folder"]] : [];
  if (name !== undefined) domain.push(["name", "=", name]);
  return domain;
}

export function orderFolderTree(
  folders: readonly DocumentFolder[],
): DocumentFolder[] {
  const byId = new Map(folders.map((folder) => [folder.id, folder]));
  const children = new Map<number | null, DocumentFolder[]>();
  for (const folder of folders) {
    const relation = relationId(folder.parent_folder_id);
    const parentId = relation !== null && byId.has(relation) ? relation : null;
    const siblings = children.get(parentId) ?? [];
    siblings.push(folder);
    children.set(parentId, siblings);
  }
  for (const siblings of children.values()) {
    siblings.sort(
      (left, right) =>
        left.name.localeCompare(right.name, "und", { sensitivity: "base" }) ||
        left.id - right.id,
    );
  }
  const result: DocumentFolder[] = [];
  const visited = new Set<number>();
  const visit = (
    folder: DocumentFolder,
    depth: number,
    parents: readonly string[],
  ): void => {
    if (visited.has(folder.id)) return;
    visited.add(folder.id);
    result.push({
      ...folder,
      depth,
      path: [...parents, folder.name].join(" / "),
    });
    for (const child of children.get(folder.id) ?? []) {
      visit(child, depth + 1, [...parents, folder.name]);
    }
  };
  for (const root of children.get(null) ?? []) visit(root, 0, []);
  for (const folder of [...folders].sort(
    (left, right) =>
      left.name.localeCompare(right.name, "und", { sensitivity: "base" }) ||
      left.id - right.id,
  )) {
    visit(folder, 0, []);
  }
  return result;
}

export function safeDocumentFilename(
  name: unknown,
  documentId: number,
): string {
  const parts = String(name ?? "")
    .replaceAll("\\", "/")
    .split("/");
  let filename = parts.at(-1) ?? "";
  filename = filename
    .replace(/[<>:"/\\|?*\u0000-\u001f]/gu, "_")
    .replace(/[. ]+$/u, "");
  const stem = filename.split(".", 1)[0]?.toLocaleUpperCase("und") ?? "";
  if (WINDOWS_RESERVED_NAMES.has(stem)) filename = `_${filename}`;
  return filename === "" || filename === "." || filename === ".."
    ? `document_${documentId}`
    : filename;
}

function guessMimetype(name: string): string {
  const extension = name.split(".").at(-1)?.toLocaleLowerCase("und");
  const known: Readonly<Record<string, string>> = {
    csv: "text/csv",
    gif: "image/gif",
    html: "text/html",
    jpeg: "image/jpeg",
    jpg: "image/jpeg",
    json: "application/json",
    md: "text/markdown",
    pdf: "application/pdf",
    png: "image/png",
    svg: "image/svg+xml",
    txt: "text/plain",
    webp: "image/webp",
    xml: "application/xml",
    zip: "application/zip",
  };
  return extension === undefined
    ? "application/octet-stream"
    : (known[extension] ?? "application/octet-stream");
}

export class DocumentNamespace extends GeneratedDocumentNamespace {
  private modernFolders: boolean | undefined;

  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<DocumentRecord[]> {
    return (await super.list(options)) as DocumentRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<DocumentRecord> {
    return (await super.get(recordId, fields)) as DocumentRecord;
  }

  async folders(options: FolderListOptions = {}): Promise<DocumentFolder[]> {
    const modern = await this.usesDocumentFolderRecords();
    const model = modern ? "documents.document" : "documents.folder";
    const records = await this.client.searchRead(model, {
      domain: folderDomain(modern),
      fields: modern ? MODERN_FOLDER_FIELDS : LEGACY_FOLDER_FIELDS,
      limit: options.limit === undefined ? 50 : options.limit,
      order: "name, id",
    });
    const folders = records
      .filter(
        (record): record is OdooRecord & { id: number; name: string } =>
          typeof record.id === "number" && typeof record.name === "string",
      )
      .map<DocumentFolder>((record) =>
        modern
          ? {
              id: record.id,
              name: record.name,
              parent_folder_id: record.folder_id,
            }
          : { ...record },
      );
    return options.tree === true ? orderFolderTree(folders) : folders;
  }

  resolveFolder(folder: number | string): Promise<number> {
    return this.resolveFolderInput({ folder });
  }

  async upload(
    data: BinaryInput,
    name: string,
    options: DocumentUploadOptions,
  ): Promise<number> {
    const folderId = await this.resolveFolderInput(options);
    const tagIds: number[] = [];
    for (const tag of options.tags ?? []) {
      tagIds.push(await this.resolveNamedRecord("documents.tag", tag));
    }
    const ownerId =
      options.owner === undefined
        ? undefined
        : await this.resolveNamedRecord("res.users", options.owner);
    const bytes = await binaryBytes(data);
    const values: Record<string, unknown> = {
      name,
      datas: encodeBase64(bytes),
      mimetype:
        options.mimetype ??
        (typeof Blob !== "undefined" && data instanceof Blob && data.type !== ""
          ? data.type
          : guessMimetype(name)),
      folder_id: folderId,
    };
    if (tagIds.length > 0) values.tag_ids = [Cmd.set(tagIds)];
    if (ownerId !== undefined) values.owner_id = ownerId;
    return this.client.create("documents.document", values);
  }

  /** Worker adaptation of Python download_file: return sanitized name and bytes. */
  async downloadFile(documentId: number): Promise<DownloadedDocument> {
    const records = await this.client.read(
      "documents.document",
      [documentId],
      ["name", "type", "file_size", "datas", "mimetype"],
    );
    const document = records[0];
    if (document === undefined) {
      throw new RecordNotFoundError("documents.document", documentId);
    }
    let data: Uint8Array;
    if (typeof document.datas === "string") {
      data = decodeBase64(document.datas);
    } else if (document.type === "binary" && document.file_size === 0) {
      data = new Uint8Array();
    } else {
      throw new RecordNotFoundError("documents.document", documentId);
    }
    const result: DownloadedDocument = {
      id: documentId,
      name: safeDocumentFilename(document.name, documentId),
      data,
    };
    return typeof document.mimetype === "string"
      ? { ...result, mimetype: document.mimetype }
      : result;
  }

  private async usesDocumentFolderRecords(): Promise<boolean> {
    if (this.modernFolders !== undefined) return this.modernFolders;
    const fields = await this.client.fieldsGet(
      "documents.document",
      ["type"],
      ["selection"],
    );
    this.modernFolders = selectionIncludesFolder(fields);
    return this.modernFolders;
  }

  private async resolveFolderInput(options: {
    folder?: number | string;
    folderId?: number;
  }): Promise<number> {
    if ((options.folder === undefined) === (options.folderId === undefined)) {
      throw new VodooError("Specify exactly one of folder or folderId");
    }
    if (options.folderId !== undefined) {
      const direct = numericId(options.folderId);
      if (direct === null)
        throw new VodooError("folderId must be a positive integer");
      return direct;
    }
    const folder = options.folder;
    if (folder === undefined) throw new VodooError("Specify a folder");
    const direct = numericId(folder);
    if (direct !== null) return direct;
    if (typeof folder !== "string") throw new VodooError("Invalid folder name");
    const modern = await this.usesDocumentFolderRecords();
    const model = modern ? "documents.document" : "documents.folder";
    const records = await this.client.searchRead(model, {
      domain: folderDomain(modern, folder),
      fields: ["id", "name"],
      limit: 2,
    });
    return requireUniqueId(records, model, folder);
  }

  private async resolveNamedRecord(
    model: string,
    value: number | string,
  ): Promise<number> {
    const direct = numericId(value);
    if (direct !== null) return direct;
    if (typeof value !== "string")
      throw new VodooError(`Invalid ${model} name`);
    const domain: Domain =
      model === "res.users"
        ? ["|", ["login", "=", value], ["name", "=", value]]
        : [["name", "=", value]];
    const fields =
      model === "res.users" ? ["id", "name", "login"] : ["id", "name"];
    const records = await this.client.searchRead(model, {
      domain,
      fields,
      limit: 2,
    });
    return requireUniqueId(records, model, value);
  }
}
