import type { OdooRecord } from "./types.js";

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/u;
const DATETIME_RE = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$/u;

function requireValidDate(value: Date, label: string): Date {
  if (Number.isNaN(value.getTime())) {
    throw new TypeError(`Invalid ${label}`);
  }
  return value;
}

function parseParts(
  value: string,
  match: RegExpMatchArray,
  hasTime: boolean,
): Date {
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = hasTime ? Number(match[4]) : 0;
  const minute = hasTime ? Number(match[5]) : 0;
  const second = hasTime ? Number(match[6]) : 0;
  const parsed = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  if (
    parsed.getUTCFullYear() !== year ||
    parsed.getUTCMonth() !== month - 1 ||
    parsed.getUTCDate() !== day ||
    parsed.getUTCHours() !== hour ||
    parsed.getUTCMinutes() !== minute ||
    parsed.getUTCSeconds() !== second
  ) {
    throw new TypeError(
      `Invalid Odoo ${hasTime ? "datetime" : "date"}: ${value}`,
    );
  }
  return parsed;
}

export function parseOdooDate(value: string): Date {
  const match = value.match(DATE_RE);
  if (match === null) {
    throw new TypeError(`Invalid Odoo date: ${value}`);
  }
  return parseParts(value, match, false);
}

export function parseOdooDateTime(value: string): Date {
  const match = value.match(DATETIME_RE);
  if (match === null) {
    throw new TypeError(`Invalid Odoo datetime: ${value}`);
  }
  return parseParts(value, match, true);
}

function pad(value: number): string {
  return String(value).padStart(2, "0");
}

export function formatOdooDate(value: Date): string {
  const date = requireValidDate(value, "Date");
  return `${date.getUTCFullYear()}-${pad(date.getUTCMonth() + 1)}-${pad(date.getUTCDate())}`;
}

export function formatOdooDateTime(value: Date): string {
  const date = requireValidDate(value, "Date");
  return `${formatOdooDate(date)} ${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}:${pad(date.getUTCSeconds())}`;
}

export type DateFieldKind = "date" | "datetime";

export function decodeRecordDates<T extends OdooRecord>(
  record: T,
  dateFields: Readonly<Record<string, DateFieldKind>>,
): T {
  const result: OdooRecord = { ...record };
  for (const [field, kind] of Object.entries(dateFields)) {
    const value = result[field];
    if (value === false || value === null) {
      result[field] = null;
    } else if (typeof value === "string") {
      result[field] =
        kind === "date" ? parseOdooDate(value) : parseOdooDateTime(value);
    }
  }
  return result as T;
}
