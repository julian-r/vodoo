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
        ["mail.message.subtype", 4],
        91,
        [{ partner_id: 8 }],
        ["mail.message.subtype", 5],
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
      method: "execute",
      args: [
        "ir.model.data",
        "check_object_reference",
        [],
        { module: "mail", xml_id: "mt_comment", raise_on_access_error: true },
      ],
    });
    expect(client.calls[4]).toMatchObject({
      method: "execute",
      args: [
        "ir.model.data",
        "check_object_reference",
        [],
        { module: "mail", xml_id: "mt_note", raise_on_access_error: true },
      ],
    });
    expect(client.calls.some((call) => call.method === "searchRead")).toBe(
      false,
    );
  });

  it.each([
    { label: "missing", rows: [] },
    { label: "zero", rows: ["mail.message.subtype", 0] },
    { label: "negative", rows: ["mail.message.subtype", -1] },
    { label: "boolean", rows: ["mail.message.subtype", false] },
    { label: "wrong model", rows: ["res.users", 1] },
    { label: "short", rows: ["mail.message.subtype"] },
    { label: "long", rows: ["mail.message.subtype", 1, 2] },
    { label: "fractional", rows: ["mail.message.subtype", 1.5] },
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
      expect(client.calls.some((call) => call.method === "create")).toBe(false);
    },
  );

  it("requires a configured message user", async () => {
    await expect(
      messagePostSudo(new RecordingClient(), "project.task", 2, "x"),
    ).rejects.toBeInstanceOf(ConfigurationError);
  });
});
