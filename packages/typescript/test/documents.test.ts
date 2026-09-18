import { describe, expect, it } from "vitest";

import {
  DocumentNamespace,
  orderFolderTree,
  safeDocumentFilename,
} from "../src/namespaces/documents.js";
import { RecordingClient } from "../src/testing.js";

describe("DocumentNamespace", () => {
  it("probes the modern folder schema and builds a stable tree", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      {
        type: {
          selection: [
            ["binary", "File"],
            ["folder", "Folder"],
          ],
        },
      },
      [
        { id: 3, name: "Child", folder_id: [2, "Root"] },
        { id: 2, name: "Root", folder_id: false },
      ],
    ]);
    const documents = new DocumentNamespace(client);

    await expect(
      documents.folders({ tree: true, limit: null }),
    ).resolves.toEqual([
      expect.objectContaining({ id: 2, depth: 0, path: "Root" }),
      expect.objectContaining({
        id: 3,
        parent_folder_id: [2, "Root"],
        depth: 1,
        path: "Root / Child",
      }),
    ]);
    expect(client.calls).toEqual([
      {
        method: "fieldsGet",
        args: ["documents.document", ["type"], ["selection"]],
      },
      {
        method: "searchRead",
        args: [
          "documents.document",
          {
            domain: [["type", "=", "folder"]],
            fields: ["id", "name", "folder_id"],
            limit: null,
            order: "name, id",
          },
        ],
      },
    ]);
  });

  it("resolves legacy folder names and rejects ambiguous matches", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      { type: { selection: [["binary", "File"]] } },
      [
        { id: 4, name: "Shared" },
        { id: 5, name: "Shared" },
      ],
    ]);
    const documents = new DocumentNamespace(client);

    await expect(documents.resolveFolder("Shared")).rejects.toThrow(
      "Multiple documents.folder records match 'Shared'",
    );
  });

  it("uploads bytes with web-native values", async () => {
    const client = new RecordingClient("https://odoo.example.com", [44]);
    const documents = new DocumentNamespace(client);

    await expect(
      documents.upload(new Uint8Array([1, 2, 3]), "report.pdf", {
        folderId: 9,
        tags: [5, 6],
        owner: 7,
      }),
    ).resolves.toBe(44);
    expect(client.calls).toEqual([
      {
        method: "create",
        args: [
          "documents.document",
          {
            name: "report.pdf",
            datas: "AQID",
            mimetype: "application/pdf",
            folder_id: 9,
            tag_ids: [[6, 0, [5, 6]]],
            owner_id: 7,
          },
          undefined,
        ],
      },
    ]);
  });

  it("downloads binary data in memory and sanitizes the filename", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      [
        {
          id: 8,
          name: "../../CON.txt ",
          type: "binary",
          datas: "SGk=",
          mimetype: "text/plain",
        },
      ],
    ]);
    const documents = new DocumentNamespace(client);

    const result = await documents.downloadFile(8);
    expect(result.name).toBe("_CON.txt");
    expect([...result.data]).toEqual([72, 105]);
    expect(result.mimetype).toBe("text/plain");
  });

  it("handles zero-byte files and deterministic malformed trees", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      [{ id: 12, name: "", type: "binary", file_size: 0, datas: false }],
    ]);
    const documents = new DocumentNamespace(client);

    await expect(documents.downloadFile(12)).resolves.toEqual({
      id: 12,
      name: "document_12",
      data: new Uint8Array(),
    });
    expect(
      orderFolderTree([
        { id: 2, name: "Cycle B", parent_folder_id: [1, "Cycle A"] },
        { id: 1, name: "Cycle A", parent_folder_id: [2, "Cycle B"] },
      ]).map((folder) => folder.id),
    ).toEqual([1, 2]);
    expect(safeDocumentFilename("../NUL", 3)).toBe("_NUL");
  });

  it("requires exactly one folder selector", async () => {
    const documents = new DocumentNamespace(new RecordingClient());
    await expect(
      documents.upload(new Uint8Array(), "x.txt", { folder: 1, folderId: 1 }),
    ).rejects.toThrow("Specify exactly one of folder or folderId");
  });
});
