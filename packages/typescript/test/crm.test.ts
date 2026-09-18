import { describe, expect, it } from "vitest";

import {
  CRMNamespace,
  buildPipelineSummary,
  computeHealthFlags,
} from "../src/namespaces/crm.js";
import { RecordingClient } from "../src/testing.js";

describe("CRMNamespace", () => {
  it("creates opportunities and lists filtered stages", async () => {
    const client = new RecordingClient(undefined, [
      19,
      [{ id: 2, name: "Won" }],
    ]);
    const crm = new CRMNamespace(client);
    await expect(
      crm.create("Renewal", {
        expectedRevenue: 5000,
        tagIds: [3],
        teamId: 4,
        extraFields: { priority: "2" },
      }),
    ).resolves.toBe(19);
    await expect(crm.stages(4)).resolves.toEqual([{ id: 2, name: "Won" }]);
    expect(client.calls[0]).toEqual({
      method: "create",
      args: [
        "crm.lead",
        {
          name: "Renewal",
          type: "opportunity",
          priority: "2",
          expected_revenue: 5000,
          team_id: 4,
          tag_ids: [[6, 0, [3]]],
        },
        undefined,
      ],
    });
    expect(client.calls[1]).toEqual({
      method: "searchRead",
      args: [
        "crm.stage",
        {
          domain: [["team_id", "=", 4]],
          fields: ["id", "name", "sequence", "is_won", "fold"],
          order: "sequence",
        },
      ],
    });
  });

  it("fetches and aggregates pipeline records with native datetimes", async () => {
    const client = new RecordingClient(undefined, [
      [
        {
          id: 9,
          name: "Renewal",
          stage_id: [2, "Qualified"],
          expected_revenue: 1000,
          probability: 25,
          create_date: "2026-01-01 00:00:00",
          partner_id: [4, "Acme"],
          user_id: [5, "Ada"],
        },
      ],
      [{ id: 2, name: "Qualified", sequence: 10 }],
    ]);
    const summary = await new CRMNamespace(client).pipeline({ team: "Direct" });
    expect(summary.team).toBe("Direct");
    expect(summary.totals).toEqual({ deals: 1, revenue: 1000, weighted: 250 });
    expect(summary.deals[0]?.partner).toBe("Acme");
    expect(client.calls[0]?.args[1]).toMatchObject({
      domain: [
        ["type", "=", "opportunity"],
        ["team_id.name", "ilike", "Direct"],
      ],
      limit: 0,
    });
  });
});

describe("CRM pipeline pure helpers", () => {
  it("matches Python decimal rounding for IEEE-754 weighted values", () => {
    const summary = buildPipelineSummary(
      [
        {
          id: 1,
          name: "Binary float",
          stage_id: [2, "New"],
          expected_revenue: 2.675,
          probability: 100,
          create_date: new Date("2026-01-02T00:00:00Z"),
        },
      ],
      [{ id: 2, name: "New" }],
      { today: new Date("2026-01-02T00:00:00Z") },
    );
    expect(summary.stages[0]?.weighted).toBe(2.67);
    expect(summary.totals.weighted).toBe(2.67);
  });

  it("uses Python half-even rounding for aggregate ties", () => {
    const summary = buildPipelineSummary(
      [
        {
          id: 1,
          name: "Today",
          stage_id: [2, "New"],
          create_date: new Date("2026-01-02T00:00:00Z"),
        },
        {
          id: 2,
          name: "Yesterday",
          stage_id: [2, "New"],
          create_date: new Date("2026-01-01T00:00:00Z"),
        },
      ],
      [{ id: 2, name: "New" }],
      { today: new Date("2026-01-02T00:00:00Z") },
    );
    expect(summary.stages[0]?.avgAgeDays).toBe(0);
  });

  it("summarizes and health-checks deals deterministically", () => {
    const summary = buildPipelineSummary(
      [
        {
          id: 1,
          name: "Unowned",
          stage_id: [3, "Qualified"],
          expected_revenue: 0,
          probability: 0,
          create_date: new Date("2025-01-01T00:00:00Z"),
          partner_id: null,
          user_id: null,
        },
      ],
      [
        { id: 2, name: "New" },
        { id: 3, name: "Qualified" },
      ],
      { today: new Date("2026-01-01T00:00:00Z") },
    );
    expect(summary.stages[0]).toMatchObject({
      stageId: 3,
      deals: 1,
      revenue: 0,
    });
    const flags = computeHealthFlags(summary);
    expect(flags.map((flag) => flag.rule)).toEqual([
      "Zero probability",
      "No partner",
      "No salesperson",
      "Stale deal",
    ]);
    expect(flags.at(-1)?.detail).toBe("365d in first stage (threshold: 30d)");
    expect(
      buildPipelineSummary([], [], {
        team: "",
        today: new Date("2026-01-01T00:00:00Z"),
      }).team,
    ).toBe("All Teams");
  });
});
