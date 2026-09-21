import { describe, expect, it, vi } from "vitest";

import { OdooClient } from "../src/client.js";
import { HTML, Markdown } from "../src/content.js";
import { AccountMoveNamespace } from "../src/namespaces/account-moves.js";
import { ActivityNamespace } from "../src/namespaces/activities.js";
import { CRMNamespace } from "../src/namespaces/crm.js";
import { DocumentNamespace } from "../src/namespaces/documents.js";
import { GenericNamespace } from "../src/namespaces/generic.js";
import { HelpdeskNamespace } from "../src/namespaces/helpdesk.js";
import { KnowledgeNamespace } from "../src/namespaces/knowledge.js";
import { ProjectNamespace } from "../src/namespaces/projects.js";
import { SecurityNamespace } from "../src/namespaces/security.js";
import { TaskNamespace } from "../src/namespaces/tasks.js";
import { TimerNamespace } from "../src/namespaces/timer.js";
import type { OdooTransportApi } from "../src/transport.js";

function makeTransport(): OdooTransportApi {
  return {
    dialect: "jsonrpc",
    getUid: vi.fn(async () => 7),
    authenticate: vi.fn(async () => 7),
    executeKw: vi.fn(async () => ({ name: { type: "char" } })),
    search: vi.fn(async () => [1, 2]),
    read: vi.fn(async () => [{ id: 1, partner_id: false, active: false }]),
    searchRead: vi.fn(async () => [{ id: 1, partner_id: false }]),
    create: vi.fn(async () => 3),
    write: vi.fn(async () => true),
    unlink: vi.fn(async () => true),
    nameSearch: vi.fn(async () => [[1, "One"] as const]),
    close: vi.fn(async () => undefined),
  };
}

const config = {
  url: "https://odoo.example.com",
  database: "db",
  username: "bot@example.com",
  password: "secret",
};

describe("OdooClient generic API", () => {
  it("delegates every generic operation and exposes namespaces", async () => {
    const transport = makeTransport();
    const client = new OdooClient(config, { transport });

    expect(client.helpdesk).toBeInstanceOf(HelpdeskNamespace);
    expect(client.crm).toBeInstanceOf(CRMNamespace);
    expect(client.tasks).toBeInstanceOf(TaskNamespace);
    expect(client.projects).toBeInstanceOf(ProjectNamespace);
    expect(client.accountMoves).toBeInstanceOf(AccountMoveNamespace);
    expect(client.activities).toBeInstanceOf(ActivityNamespace);
    expect(client.documents).toBeInstanceOf(DocumentNamespace);
    expect(client.knowledge).toBeInstanceOf(KnowledgeNamespace);
    expect(client.timer).toBeInstanceOf(TimerNamespace);
    expect(client.security).toBeInstanceOf(SecurityNamespace);
    expect(client.generic).toBeInstanceOf(GenericNamespace);
    await expect(client.getUid()).resolves.toBe(7);
    await client.execute("res.partner", "custom", [[1]], { flag: true });
    await client.executeWithUserContext("res.partner", "custom", 9, [[1]], {
      context: { lang: "en_US" },
    });
    await expect(client.search("res.partner", { limit: 2 })).resolves.toEqual([
      1, 2,
    ]);
    await expect(client.read("res.partner", [1])).resolves.toEqual([
      { id: 1, partner_id: null, active: null },
    ]);
    await expect(
      client.searchRead("res.partner", { fields: ["id"] }),
    ).resolves.toEqual([{ id: 1, partner_id: null }]);
    await expect(
      client.create("res.partner", {
        name: "One",
        description: new Markdown("**Created**"),
      }),
    ).resolves.toBe(3);
    await expect(
      client.write("res.partner", [1], {
        name: "Two",
        description: new HTML("<b>Updated</b>"),
      }),
    ).resolves.toBe(true);
    await expect(client.unlink("res.partner", [1])).resolves.toBe(true);
    await expect(
      client.fieldsGet("res.partner", ["name"], ["type"]),
    ).resolves.toEqual({
      name: { type: "char" },
    });
    await expect(client.nameSearch("res.partner", "One")).resolves.toEqual([
      [1, "One"],
    ]);
    await client.close();

    expect(transport.create).toHaveBeenCalledWith(
      "res.partner",
      { name: "One", description: "<p><strong>Created</strong></p>" },
      null,
    );
    expect(transport.write).toHaveBeenCalledWith("res.partner", [1], {
      name: "Two",
      description: "<b>Updated</b>",
    });
    expect(transport.executeKw).toHaveBeenNthCalledWith(
      1,
      "res.partner",
      "custom",
      [[1]],
      {
        flag: true,
      },
    );
    expect(transport.executeKw).toHaveBeenNthCalledWith(
      2,
      "res.partner",
      "custom",
      [[1]],
      { context: { lang: "en_US", sudo_user_id: 9 } },
    );
    expect(transport.executeKw).toHaveBeenNthCalledWith(
      3,
      "res.partner",
      "fields_get",
      [["name"]],
      { attributes: ["type"] },
    );
    expect(transport.close).toHaveBeenCalledOnce();
  });
});
