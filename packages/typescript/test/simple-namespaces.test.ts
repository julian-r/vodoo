import { describe, expect, it } from "vitest";

import { GenericNamespace } from "../src/namespaces/generic.js";
import { HelpdeskNamespace } from "../src/namespaces/helpdesk.js";
import { KnowledgeNamespace } from "../src/namespaces/knowledge.js";
import { RecordingClient } from "../src/testing.js";

describe("HelpdeskNamespace", () => {
  it("creates tickets with x2many tags and decodes datetimes", async () => {
    const client = new RecordingClient(undefined, [
      31,
      [{ id: 31, name: "Broken", create_date: "2026-01-02 03:04:05" }],
    ]);
    const helpdesk = new HelpdeskNamespace(client);
    await expect(
      helpdesk.create("Broken", {
        description: "Details",
        partnerId: 2,
        tagIds: [4, 5],
        teamId: 7,
        extraFields: { priority: "3" },
      }),
    ).resolves.toBe(31);
    const records = await helpdesk.list();
    expect(records[0]?.create_date).toEqual(new Date("2026-01-02T03:04:05Z"));
    expect(client.calls[0]).toEqual({
      method: "create",
      args: [
        "helpdesk.ticket",
        {
          name: "Broken",
          priority: "3",
          description: "Details",
          partner_id: 2,
          tag_ids: [[6, 0, [4, 5]]],
          team_id: 7,
        },
        undefined,
      ],
    });
  });
});

describe("KnowledgeNamespace", () => {
  it("creates Markdown articles", async () => {
    const client = new RecordingClient(undefined, [44]);
    await expect(
      new KnowledgeNamespace(client).create("Runbook", {
        body: "# Deploy",
        parentId: 2,
        category: "workspace",
        icon: "📘",
      }),
    ).resolves.toBe(44);
    expect(client.calls[0]).toEqual({
      method: "create",
      args: [
        "knowledge.article",
        {
          name: "Runbook",
          body: "<h1>Deploy</h1>",
          parent_id: 2,
          category: "workspace",
          icon: "📘",
        },
        undefined,
      ],
    });
  });

  it("resolves article_url with a synchronous URL fallback", async () => {
    const client = new RecordingClient(
      "https://odoo.example.com/",
      [
        [{ id: 4, article_url: "/knowledge/article/4" }],
        [{ id: 5, article_url: false }],
      ],
      undefined,
      true,
    );
    const knowledge = new KnowledgeNamespace(client);
    await expect(knowledge.resolveUrl(4)).resolves.toBe("/knowledge/article/4");
    await expect(knowledge.resolveUrl(5)).resolves.toBe(
      "https://odoo.example.com/odoo/knowledge.article/5",
    );
  });
});

describe("GenericNamespace", () => {
  it("forwards arbitrary model operations", async () => {
    const client = new RecordingClient(undefined, [
      8,
      true,
      true,
      [{ id: 8, name: "Acme" }],
      [8, "Acme"],
    ]);
    const generic = new GenericNamespace(client);
    await expect(generic.create("res.partner", { name: "Acme" })).resolves.toBe(
      8,
    );
    await expect(
      generic.update("res.partner", 8, { phone: "+1" }),
    ).resolves.toBe(true);
    await expect(generic.delete("res.partner", 8)).resolves.toBe(true);
    await expect(
      generic.search("res.partner", { domain: [["name", "=", "Acme"]] }),
    ).resolves.toEqual([{ id: 8, name: "Acme" }]);
    await expect(
      generic.call("res.partner", "name_get", [[8]], { lang: "en_US" }),
    ).resolves.toEqual([8, "Acme"]);
    expect(client.calls.map((call) => call.method)).toEqual([
      "create",
      "write",
      "unlink",
      "searchRead",
      "execute",
    ]);
  });
});
