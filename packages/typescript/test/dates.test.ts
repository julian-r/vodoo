import { describe, expect, it } from "vitest";

import {
  decodeRecordDates,
  formatOdooDate,
  formatOdooDateTime,
  parseOdooDate,
  parseOdooDateTime,
} from "../src/dates.js";

describe("Odoo date codecs", () => {
  it("round-trips date-only values at UTC midnight", () => {
    const value = parseOdooDate("2026-04-30");
    expect(value.toISOString()).toBe("2026-04-30T00:00:00.000Z");
    expect(formatOdooDate(value)).toBe("2026-04-30");
  });

  it("round-trips Odoo datetimes as UTC", () => {
    const value = parseOdooDateTime("2026-04-30 12:34:56");
    expect(value.toISOString()).toBe("2026-04-30T12:34:56.000Z");
    expect(formatOdooDateTime(value)).toBe("2026-04-30 12:34:56");
  });

  it.each(["2026-02-30", "30-04-2026", "2026-4-3"])(
    "rejects invalid dates: %s",
    (value) => {
      expect(() => parseOdooDate(value)).toThrow(TypeError);
    },
  );

  it("normalizes Odoo false values to null for typed date fields", () => {
    expect(
      decodeRecordDates(
        { deadline: false, reached_date: null },
        { deadline: "date", reached_date: "date" },
      ),
    ).toEqual({ deadline: null, reached_date: null });
  });

  it("rejects invalid Date objects", () => {
    expect(() => formatOdooDate(new Date(Number.NaN))).toThrow(TypeError);
  });
});
