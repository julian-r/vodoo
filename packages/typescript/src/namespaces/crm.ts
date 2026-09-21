import type { OdooClientApi } from "../client-api.js";
import { Cmd } from "../commands.js";
import { decodeRecordDates, formatOdooDate } from "../dates.js";
import { GeneratedCRMNamespace } from "../generated/crm.js";
import type { OdooRecord } from "../types.js";
import type { ListOptions } from "./domain.js";

const PIPELINE_FIELDS = [
  "id",
  "name",
  "stage_id",
  "expected_revenue",
  "probability",
  "create_date",
  "partner_id",
  "user_id",
  "team_id",
] as const;

export interface StaleThresholds {
  _first?: number;
  _middle?: number;
  _late?: number;
}

export const DEFAULT_STALE_THRESHOLDS = Object.freeze({
  _first: 30,
  _middle: 45,
  _late: 60,
});

export interface CRMRecord extends OdooRecord {
  id: number;
  name: string;
  create_date?: Date | null;
}

export interface CRMStage extends OdooRecord {
  id: number;
  name: string;
  sequence?: number;
  is_won?: boolean | null;
  fold?: boolean | null;
}

export interface CreateCRMOptions {
  partnerId?: number;
  expectedRevenue?: number;
  stageId?: number;
  userId?: number;
  teamId?: number;
  tagIds?: readonly number[];
  leadType?: "lead" | "opportunity";
  extraFields?: Readonly<Record<string, unknown>>;
}

export interface PipelineStageSummary {
  stageId: number;
  name: string;
  deals: number;
  revenue: number;
  weighted: number;
  avgAgeDays: number;
  oldestDays: number;
}

export interface PipelineDeal {
  id: number;
  name: string;
  stageId: number | null;
  stageName: string;
  expectedRevenue: number;
  probability: number;
  ageDays: number;
  partner: string | null;
  user: string | null;
  stageOrder: number;
}

export interface PipelineSummary {
  team: string;
  date: string;
  stages: PipelineStageSummary[];
  totals: { deals: number; revenue: number; weighted: number };
  deals: PipelineDeal[];
}

export type HealthSeverity = "critical" | "warning" | "info";
export interface HealthFlag {
  severity: HealthSeverity;
  rule: string;
  dealId: number;
  dealName: string;
  detail: string;
}

function relationId(value: unknown): number | null {
  if (typeof value === "number") return value;
  if (Array.isArray(value) && typeof value[0] === "number") return value[0];
  return null;
}

function relationName(value: unknown): string | null {
  return Array.isArray(value) && typeof value[1] === "string" ? value[1] : null;
}

function numberValue(value: unknown): number {
  return typeof value === "number" ? value : 0;
}

/** Match Python's round-to-nearest, ties-to-even behavior for IEEE-754 doubles. */
function roundHalfEven(value: number, digits = 0): number {
  if (!Number.isFinite(value)) return value;
  if (!Number.isInteger(digits) || digits < 0) {
    throw new RangeError("digits must be a non-negative integer");
  }

  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, Math.abs(value), false);
  const bits = view.getBigUint64(0, false);
  const exponentBits = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & ((1n << 52n) - 1n);
  if (exponentBits === 0 && fraction === 0n) return value;

  const significand = exponentBits === 0 ? fraction : fraction | (1n << 52n);
  const binaryExponent =
    (exponentBits === 0 ? 1 - 1023 : exponentBits - 1023) - 52;
  const decimalFactor = 10n ** BigInt(digits);
  let numerator = significand * decimalFactor;
  let denominator = 1n;
  if (binaryExponent >= 0) {
    numerator <<= BigInt(binaryExponent);
  } else {
    denominator <<= BigInt(-binaryExponent);
  }

  let quotient = numerator / denominator;
  const doubledRemainder = (numerator % denominator) * 2n;
  if (
    doubledRemainder > denominator ||
    (doubledRemainder === denominator && quotient % 2n !== 0n)
  ) {
    quotient += 1n;
  }
  if (value < 0) quotient = -quotient;
  return Number(quotient) / 10 ** digits;
}

function ageDays(value: unknown, today: Date): number {
  if (!(value instanceof Date) || Number.isNaN(value.getTime())) return 0;
  const start = Date.UTC(
    value.getUTCFullYear(),
    value.getUTCMonth(),
    value.getUTCDate(),
  );
  const end = Date.UTC(
    today.getUTCFullYear(),
    today.getUTCMonth(),
    today.getUTCDate(),
  );
  return Math.floor((end - start) / 86_400_000);
}

export function buildPipelineSummary(
  deals: readonly OdooRecord[],
  stages: readonly OdooRecord[],
  options: { team?: string; today?: Date } = {},
): PipelineSummary {
  const today = options.today ?? new Date();
  const stageOrder = new Map<number, number>();
  const stageNames = new Map<number, string>();
  stages.forEach((stage, index) => {
    if (typeof stage.id === "number") {
      stageOrder.set(stage.id, index);
      stageNames.set(stage.id, String(stage.name ?? `Stage ${stage.id}`));
    }
  });

  const byStage = new Map<number, OdooRecord[]>();
  for (const deal of deals) {
    const stageId = relationId(deal.stage_id);
    if (stageId === null) continue;
    const current = byStage.get(stageId) ?? [];
    current.push(deal);
    byStage.set(stageId, current);
  }

  const stageSummaries: PipelineStageSummary[] = [];
  let totalDeals = 0;
  let totalRevenue = 0;
  let totalWeighted = 0;
  for (const stage of stages) {
    if (typeof stage.id !== "number") continue;
    const stageDeals = byStage.get(stage.id) ?? [];
    if (stageDeals.length === 0) continue;
    const revenue = stageDeals.reduce(
      (total, deal) => total + numberValue(deal.expected_revenue),
      0,
    );
    const weighted = stageDeals.reduce(
      (total, deal) =>
        total +
        (numberValue(deal.expected_revenue) * numberValue(deal.probability)) /
          100,
      0,
    );
    const ages = stageDeals.map((deal) => ageDays(deal.create_date, today));
    stageSummaries.push({
      stageId: stage.id,
      name: stageNames.get(stage.id) ?? `Stage ${stage.id}`,
      deals: stageDeals.length,
      revenue,
      weighted: roundHalfEven(weighted, 2),
      avgAgeDays: roundHalfEven(
        ages.reduce((total, age) => total + age, 0) / stageDeals.length,
      ),
      oldestDays: Math.max(...ages),
    });
    totalDeals += stageDeals.length;
    totalRevenue += revenue;
    totalWeighted += weighted;
  }

  const enrichedDeals: PipelineDeal[] = deals
    .filter((deal): deal is OdooRecord & { id: number } =>
      Number.isInteger(deal.id),
    )
    .map((deal) => {
      const stageId = relationId(deal.stage_id);
      return {
        id: deal.id,
        name: String(deal.name ?? ""),
        stageId,
        stageName: stageId === null ? "" : (stageNames.get(stageId) ?? ""),
        expectedRevenue: numberValue(deal.expected_revenue),
        probability: numberValue(deal.probability),
        ageDays: ageDays(deal.create_date, today),
        partner: relationName(deal.partner_id),
        user: relationName(deal.user_id),
        stageOrder: stageId === null ? 999 : (stageOrder.get(stageId) ?? 999),
      };
    })
    .sort(
      (left, right) =>
        left.stageOrder - right.stageOrder ||
        right.expectedRevenue - left.expectedRevenue,
    );

  return {
    team:
      options.team === undefined || options.team === ""
        ? "All Teams"
        : options.team,
    date: formatOdooDate(today),
    stages: stageSummaries,
    totals: {
      deals: totalDeals,
      revenue: totalRevenue,
      weighted: roundHalfEven(totalWeighted, 2),
    },
    deals: enrichedDeals,
  };
}

export function computeHealthFlags(
  summary: PipelineSummary,
  thresholds: Readonly<StaleThresholds> = DEFAULT_STALE_THRESHOLDS,
): HealthFlag[] {
  const firstThreshold = thresholds._first ?? 30;
  const middleThreshold = thresholds._middle ?? 45;
  const lateThreshold = thresholds._late ?? 60;
  const stagePositions = new Map(
    summary.stages.map((stage, index) => [stage.stageId, index]),
  );
  const severityOrder: Record<HealthSeverity, number> = {
    critical: 0,
    warning: 1,
    info: 2,
  };
  const flags: HealthFlag[] = [];
  for (const deal of summary.deals) {
    const position =
      deal.stageId === null ? 0 : (stagePositions.get(deal.stageId) ?? 0);
    if (deal.probability === 0) {
      flags.push({
        severity: "critical",
        rule: "Zero probability",
        dealId: deal.id,
        dealName: deal.name,
        detail: "Open deal with 0% probability",
      });
    }
    if (deal.expectedRevenue === 0 && position > 0) {
      flags.push({
        severity: "warning",
        rule: "Missing revenue",
        dealId: deal.id,
        dealName: deal.name,
        detail: `No expected revenue in stage '${deal.stageName}'`,
      });
    }
    const halfway = Math.floor(summary.stages.length / 2);
    const staleThreshold =
      position === 0
        ? firstThreshold
        : position < halfway
          ? middleThreshold
          : lateThreshold;
    if (deal.ageDays > staleThreshold) {
      flags.push({
        severity: position === 0 ? "info" : "warning",
        rule: "Stale deal",
        dealId: deal.id,
        dealName: deal.name,
        detail:
          position === 0
            ? `${deal.ageDays}d in first stage (threshold: ${staleThreshold}d)`
            : `${deal.ageDays}d in '${deal.stageName}' (threshold: ${staleThreshold}d)`,
      });
    }
    if (deal.partner === null) {
      flags.push({
        severity: "warning",
        rule: "No partner",
        dealId: deal.id,
        dealName: deal.name,
        detail: "No partner linked",
      });
    }
    if (deal.user === null) {
      flags.push({
        severity: "warning",
        rule: "No salesperson",
        dealId: deal.id,
        dealName: deal.name,
        detail: "No salesperson assigned",
      });
    }
  }
  return flags.sort(
    (left, right) =>
      severityOrder[left.severity] - severityOrder[right.severity] ||
      left.dealName.localeCompare(right.dealName),
  );
}

export class CRMNamespace extends GeneratedCRMNamespace {
  constructor(client: OdooClientApi) {
    super(client);
  }

  override async list(options: ListOptions = {}): Promise<CRMRecord[]> {
    return (await super.list(options)) as CRMRecord[];
  }

  override async get(
    recordId: number,
    fields?: readonly string[],
  ): Promise<CRMRecord> {
    return (await super.get(recordId, fields)) as CRMRecord;
  }

  create(name: string, options: CreateCRMOptions = {}): Promise<number> {
    const values: Record<string, unknown> = {
      ...options.extraFields,
      name,
      type: options.leadType ?? "opportunity",
    };
    if (options.partnerId !== undefined) values.partner_id = options.partnerId;
    if (options.expectedRevenue !== undefined) {
      values.expected_revenue = options.expectedRevenue;
    }
    if (options.stageId !== undefined) values.stage_id = options.stageId;
    if (options.userId !== undefined) values.user_id = options.userId;
    if (options.teamId !== undefined) values.team_id = options.teamId;
    if (options.tagIds !== undefined)
      values.tag_ids = [Cmd.set(options.tagIds)];
    return this.client.create("crm.lead", values);
  }

  override async stages(teamId: number | null = null): Promise<CRMStage[]> {
    return (await super.stages(teamId)) as CRMStage[];
  }

  async pipeline(
    options: { team?: string; user?: string } = {},
  ): Promise<PipelineSummary> {
    const domain: Array<readonly [string, string, unknown]> = [
      ["type", "=", "opportunity"],
    ];
    if (options.team !== undefined && options.team !== "") {
      domain.push(["team_id.name", "ilike", options.team]);
    }
    if (options.user !== undefined && options.user !== "") {
      domain.push(["user_id.name", "ilike", options.user]);
    }
    const deals = await this.client.searchRead("crm.lead", {
      domain,
      fields: PIPELINE_FIELDS,
      limit: 0,
    });
    const decodedDeals = deals.map((deal) =>
      decodeRecordDates(deal, { create_date: "datetime" }),
    );
    const stages = await this.client.searchRead("crm.stage", {
      domain: [],
      fields: ["id", "name", "sequence", "is_won", "fold"],
      order: "sequence",
    });
    const summaryOptions =
      options.team === undefined ? {} : { team: options.team };
    return buildPipelineSummary(decodedDeals, stages, summaryOptions);
  }
}
