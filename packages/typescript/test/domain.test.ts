import { describe, expect, it } from "vitest";

import { ConfigurationError, VodooError } from "../src/errors.js";
import { ActivityNamespace } from "../src/namespaces/activities.js";
import { HelpdeskNamespace } from "../src/namespaces/helpdesk.js";
import { RecordingClient } from "../src/testing.js";

describe("DomainNamespace messaging", () => {
  it("posts comments and notes through mail.message", async () => {
    const client = new RecordingClient(
      undefined,
      [
        [{ partner_id: [9, "Author"] }],
        [{ res_id: 3 }],
        101,
        [{ partner_id: [9, "Author"] }],
        [{ res_id: 4 }],
        102,
      ],
      7,
    );
    const helpdesk = new HelpdeskNamespace(client);

    await expect(helpdesk.commentWithId(12, "**Visible**")).resolves.toBe(101);
    await expect(
      helpdesk.noteWithId(12, "<em>Internal</em>", { markdown: false }),
    ).resolves.toBe(102);

    expect(client.calls[2]).toEqual({
      method: "create",
      args: [
        "mail.message",
        {
          model: "helpdesk.ticket",
          res_id: 12,
          body: "<p><strong>Visible</strong></p>",
          message_type: "comment",
          subtype_id: 3,
          author_id: 9,
        },
        undefined,
      ],
    });
    expect(client.calls[5]).toEqual({
      method: "create",
      args: [
        "mail.message",
        {
          model: "helpdesk.ticket",
          res_id: 12,
          body: "<p>&lt;em&gt;Internal&lt;/em&gt;</p>",
          message_type: "notification",
          subtype_id: 4,
          author_id: 9,
        },
        undefined,
      ],
    });
  });

  it("requires an explicit or configured author", async () => {
    const helpdesk = new HelpdeskNamespace(new RecordingClient());
    await expect(helpdesk.comment(1, "message")).rejects.toBeInstanceOf(
      ConfigurationError,
    );
  });

  it("lists messages with UTC datetimes", async () => {
    const client = new RecordingClient(undefined, [
      [{ id: 2, date: "2026-03-04 05:06:07", body: "hello" }],
    ]);
    const records = await new HelpdeskNamespace(client).messages(12, 5);
    expect(records[0]?.date).toEqual(new Date("2026-03-04T05:06:07Z"));
  });
});

describe("DomainNamespace tags and binary attachments", () => {
  it("lists and idempotently adds tags", async () => {
    const client = new RecordingClient(undefined, [
      [{ id: 3, name: "Urgent" }],
      [{ tag_ids: [2] }],
      true,
      [{ tag_ids: [2, 3] }],
    ]);
    const helpdesk = new HelpdeskNamespace(client);
    await expect(helpdesk.tags()).resolves.toEqual([{ id: 3, name: "Urgent" }]);
    await expect(helpdesk.addTag(10, 3)).resolves.toBe(true);
    await expect(helpdesk.addTag(10, 3)).resolves.toBe(true);
    expect(client.calls[2]).toEqual({
      method: "write",
      args: ["helpdesk.ticket", [10], { tag_ids: [[6, 0, [2, 3]]] }],
    });
    expect(client.calls).toHaveLength(4);
  });

  it("rejects tags for namespaces without a tag model", async () => {
    const client = new RecordingClient();
    const namespace = new ActivityNamespace(client);
    await expect(namespace.tags()).rejects.toBeInstanceOf(VodooError);
  });

  it("preserves zero-byte attachments in single and bulk reads", async () => {
    const client = new RecordingClient(undefined, [
      [{ name: "empty.bin", datas: "", file_size: 0 }],
      [{ id: 57, name: "empty.bin", file_size: 0 }],
      [{ id: 57, name: "empty.bin", datas: false, file_size: 0 }],
    ]);
    const helpdesk = new HelpdeskNamespace(client);

    await expect(helpdesk.attachmentData(57)).resolves.toEqual(
      new Uint8Array(),
    );
    await expect(helpdesk.allAttachmentData(10)).resolves.toEqual([
      { id: 57, name: "empty.bin", data: new Uint8Array() },
    ]);
  });

  it("uploads, lists, and downloads attachments entirely in memory", async () => {
    const client = new RecordingClient(undefined, [
      55,
      [
        {
          id: 55,
          name: "note.txt",
          create_date: "2026-03-04 05:06:07",
        },
      ],
      [{ name: "note.txt", datas: "aGk=", mimetype: "text/plain" }],
      [
        { id: 55, name: "note.txt", mimetype: "text/plain" },
        { id: 56, name: "missing.bin" },
      ],
      [{ id: 55, name: "note.txt", datas: "aGk=", mimetype: "text/plain" }],
      [],
      [{ id: 55, name: "note.txt" }],
      [{ id: 55, name: "note.txt", datas: "aGk=", mimetype: "text/plain" }],
    ]);
    const helpdesk = new HelpdeskNamespace(client);

    await expect(
      helpdesk.attach(10, new Uint8Array([104, 105]), "note.txt", {
        mimetype: "text/plain",
      }),
    ).resolves.toBe(55);
    const metadata = await helpdesk.attachments(10);
    expect(metadata[0]?.create_date).toEqual(new Date("2026-03-04T05:06:07Z"));
    await expect(helpdesk.attachmentData(55)).resolves.toEqual(
      new Uint8Array([104, 105]),
    );
    const all = await helpdesk.allAttachmentData(10);
    expect(all).toEqual([
      {
        id: 55,
        name: "note.txt",
        data: new Uint8Array([104, 105]),
        mimetype: "text/plain",
      },
    ]);
    await expect(helpdesk.download(10, "txt")).resolves.toHaveLength(1);

    expect(client.calls[0]).toEqual({
      method: "create",
      args: [
        "ir.attachment",
        {
          name: "note.txt",
          datas: "aGk=",
          res_model: "helpdesk.ticket",
          res_id: 10,
          type: "binary",
          mimetype: "text/plain",
        },
        undefined,
      ],
    });
  });
});
