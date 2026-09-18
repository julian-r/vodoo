import { describe, expect, it } from "vitest";

import { ACCOUNT_MOVE_DEFAULT_FIELDS } from "../src/generated/account_moves.js";
import {
  AccountMoveNamespace,
  buildAccountMoveDomain,
} from "../src/namespaces/account-moves.js";
import { RecordingClient } from "../src/testing.js";

describe("AccountMoveNamespace", () => {
  it("uses generated fields and decodes account dates", async () => {
    const client = new RecordingClient(undefined, [
      [
        {
          id: 4,
          name: "INV/4",
          date: "2026-01-02",
          invoice_date: false,
        },
      ],
    ]);
    const records = await new AccountMoveNamespace(client).list();
    expect(records[0]?.date).toEqual(new Date("2026-01-02T00:00:00Z"));
    expect(records[0]?.invoice_date).toBeNull();
    expect(client.calls[0]).toEqual({
      method: "searchRead",
      args: [
        "account.move",
        {
          fields: ACCOUNT_MOVE_DEFAULT_FIELDS,
          limit: 50,
          order: "create_date desc",
        },
      ],
    });
  });

  it("builds Python-compatible account filters", () => {
    expect(
      buildAccountMoveDomain({
        search: "invoice",
        companyId: 2,
        partner: "Acme",
        moveType: "out_invoice",
        state: "posted",
        year: 2026,
      }),
    ).toEqual([
      "|",
      "|",
      "|",
      ["name", "ilike", "invoice"],
      ["ref", "ilike", "invoice"],
      ["payment_reference", "ilike", "invoice"],
      ["invoice_origin", "ilike", "invoice"],
      ["company_id", "=", 2],
      ["partner_id.name", "ilike", "Acme"],
      ["move_type", "=", "out_invoice"],
      ["state", "=", "posted"],
      ["date", ">=", "2026-01-01"],
      ["date", "<=", "2026-12-31"],
    ]);
  });
});
