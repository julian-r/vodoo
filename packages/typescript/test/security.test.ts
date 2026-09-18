import { describe, expect, it } from "vitest";

import {
  GROUP_DEFINITIONS,
  SecurityNamespace,
} from "../src/namespaces/security.js";
import { RecordingClient } from "../src/testing.js";

describe("SecurityNamespace", () => {
  it("contains the complete access profile catalog", () => {
    expect(GROUP_DEFINITIONS.map((group) => group.name)).toEqual([
      "API Mail Gateway",
      "API Base",
      "API CRM",
      "API Project",
      "API Knowledge",
      "API Helpdesk",
    ]);
  });

  it("idempotently provisions every available access and rule", async () => {
    const responses: unknown[] = [];
    let nextId = 100;
    for (const [groupIndex, group] of GROUP_DEFINITIONS.entries()) {
      const groupId = nextId++;
      if (groupIndex === 0) responses.push([], groupId);
      else responses.push([groupId]);
      for (const _definition of group.access) {
        responses.push([nextId++], [], nextId++);
      }
      for (const _definition of group.rules ?? []) {
        responses.push([nextId++], [], nextId++);
      }
    }
    const client = new RecordingClient("https://odoo.example.com", responses);
    const security = new SecurityNamespace(client);

    const result = await security.createGroups();
    expect(result.warnings).toEqual([]);
    expect(Object.keys(result.groupIds)).toEqual(
      GROUP_DEFINITIONS.map((group) => group.name),
    );
    const creates = client.calls.filter((call) => call.method === "create");
    expect(creates).toHaveLength(
      1 +
        GROUP_DEFINITIONS.reduce(
          (count, group) =>
            count + group.access.length + (group.rules?.length ?? 0),
          0,
        ),
    );
    expect(creates[0]?.args[0]).toBe("res.groups");
    expect(creates.some((call) => call.args[0] === "ir.model.access")).toBe(
      true,
    );
    expect(creates.some((call) => call.args[0] === "ir.rule")).toBe(true);
  });

  it("uses the Odoo 19 group field when creating users", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      { group_ids: { type: "many2many" } },
      71,
    ]);
    const security = new SecurityNamespace(client);

    await expect(
      security.createUser("API Bot", "bot@example.com", {
        password: "not-generated",
      }),
    ).resolves.toEqual({ userId: 71, password: "not-generated" });
    expect(client.calls[1]).toEqual({
      method: "create",
      args: [
        "res.users",
        {
          name: "API Bot",
          login: "bot@example.com",
          email: "bot@example.com",
          password: "not-generated",
          group_ids: [[6, 0, []]],
        },
        undefined,
      ],
    });
  });

  it("falls back to groups_id and replaces default groups", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      [{ res_id: 10 }],
      [{ res_id: 11 }],
      {},
      true,
    ]);
    const security = new SecurityNamespace(client);

    await security.assign(5, [20, 21]);
    expect(client.calls.at(-1)).toEqual({
      method: "write",
      args: [
        "res.users",
        [5],
        {
          groups_id: [
            [3, 10, 0],
            [3, 11, 0],
            [4, 20, 0],
            [4, 21, 0],
          ],
        },
      ],
    });
  });

  it("resolves users and reports missing groups without hiding them", async () => {
    const client = new RecordingClient("https://odoo.example.com", [
      [33],
      [40],
      [],
    ]);
    const security = new SecurityNamespace(client);

    await expect(
      security.resolveUser({ login: "bot@example.com" }),
    ).resolves.toBe(33);
    await expect(
      security.getGroupIds(["API Base", "Missing"]),
    ).resolves.toEqual({
      groupIds: { "API Base": 40 },
      warnings: ["Group 'Missing' not found"],
    });
  });

  it("sets explicit passwords and validates user lookup inputs", async () => {
    const client = new RecordingClient("https://odoo.example.com", [true]);
    const security = new SecurityNamespace(client);

    await expect(security.setPassword(9, "changed")).resolves.toBe("changed");
    await expect(security.resolveUser({})).rejects.toThrow(
      "Provide userId or login",
    );
  });
});
