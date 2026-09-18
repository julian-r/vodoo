import { describe, expect, it } from "vitest";

import { RecordOperationError } from "../src/errors.js";
import {
  ActivityNamespace,
  buildActivityDomain,
} from "../src/namespaces/activities.js";
import { RecordingClient } from "../src/testing.js";

describe("ActivityNamespace", () => {
  it("decodes deadlines and builds activity filters", async () => {
    const client = new RecordingClient(undefined, [
      [{ id: 8, date_deadline: "2026-05-06" }],
    ]);
    const records = await new ActivityNamespace(client).list();
    expect(records[0]?.date_deadline).toEqual(new Date("2026-05-06T00:00:00Z"));
    expect(
      buildActivityDomain({
        model: "project.task",
        user: "Ada",
        activityType: "Call",
      }),
    ).toEqual([
      ["res_model", "=", "project.task"],
      ["user_id.name", "ilike", "Ada"],
      ["activity_type_id.name", "ilike", "Call"],
    ]);
  });

  it("marks active activities done", async () => {
    const result = { type: "ir.actions.act_window_close" };
    const client = new RecordingClient(undefined, [
      [{ id: 8, active: true }],
      result,
    ]);
    await expect(new ActivityNamespace(client).done(8)).resolves.toEqual(
      result,
    );
    expect(client.calls[1]).toEqual({
      method: "execute",
      args: ["mail.activity", "action_done", [[8]], undefined],
    });
  });

  it("rejects an activity that is already done", async () => {
    const namespace = new ActivityNamespace(
      new RecordingClient(undefined, [[{ id: 8, active: false }]]),
    );
    await expect(namespace.done(8)).rejects.toBeInstanceOf(
      RecordOperationError,
    );
  });
});
