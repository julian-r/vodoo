import { describe, expect, it } from "vitest";

import {
  getDefaultUserId,
  getPartnerIdFromUser,
  messagePostSudo,
  messagePostSudoWithId,
} from "../src/auth.js";
import { ConfigurationError, RecordNotFoundError } from "../src/errors.js";
import { RecordingClient } from "../src/testing.js";

describe("authentication helpers", () => {
  it("resolves default users and their partners", async () => {
    const client = new RecordingClient(undefined, [
      [7],
      [{ partner_id: [8, "Ada"] }],
    ]);
    await expect(getDefaultUserId(client)).resolves.toBe(7);
    await expect(getPartnerIdFromUser(client, 7)).resolves.toBe(8);
  });

  it("reports missing users and partners", async () => {
    await expect(
      getDefaultUserId(new RecordingClient(undefined, [[]])),
    ).rejects.toBeInstanceOf(RecordNotFoundError);
    await expect(
      getPartnerIdFromUser(
        new RecordingClient(undefined, [[{ partner_id: false }]]),
        7,
      ),
    ).rejects.toBeInstanceOf(RecordNotFoundError);
  });

  it("posts comments and notes with typed values taking precedence", async () => {
    const client = new RecordingClient(
      undefined,
      [
        [{ partner_id: 8 }],
        [{ res_id: 4 }],
        91,
        [{ partner_id: 8 }],
        [{ res_id: 5 }],
        92,
      ],
      7,
    );
    await expect(
      messagePostSudoWithId(client, "project.task", 2, "<p>Done</p>", {
        extraValues: { model: "ignored", subject: "Status" },
      }),
    ).resolves.toBe(91);
    await expect(
      messagePostSudo(client, "project.task", 2, "<p>Note</p>", {
        isNote: true,
      }),
    ).resolves.toBe(true);
    expect(client.calls[2]?.args[1]).toMatchObject({
      model: "project.task",
      message_type: "comment",
      subject: "Status",
      author_id: 8,
    });
    expect(client.calls[5]?.args[1]).toMatchObject({
      message_type: "notification",
      subtype_id: 5,
    });
    expect(client.calls[1]).toMatchObject({
      method: "searchRead",
      args: [
        "ir.model.data",
        {
          domain: [
            ["module", "=", "mail"],
            ["name", "=", "mt_comment"],
          ],
          fields: ["res_id"],
          limit: 1,
        },
      ],
    });
  });

  it.each([
    { label: "missing", rows: [] },
    { label: "zero", rows: [{ res_id: 0 }] },
    { label: "negative", rows: [{ res_id: -1 }] },
    { label: "boolean", rows: [{ res_id: false }] },
  ])(
    "requires a positive stable message subtype external ID for $label",
    async ({ rows: subtypeRows }) => {
      const client = new RecordingClient(
        undefined,
        [[{ partner_id: 8 }], subtypeRows],
        7,
      );
      await expect(
        messagePostSudo(client, "project.task", 2, "x"),
      ).rejects.toBeInstanceOf(RecordNotFoundError);
    },
  );

  it("requires a configured message user", async () => {
    await expect(
      messagePostSudo(new RecordingClient(), "project.task", 2, "x"),
    ).rejects.toBeInstanceOf(ConfigurationError);
  });
});
