import type { OdooClientApi } from "../client-api.js";
import { formatOdooDate, parseOdooDate, parseOdooDateTime } from "../dates.js";
import { VodooError } from "../errors.js";
import type { Domain, OdooRecord } from "../types.js";

export const TIMESHEET_MODEL = "account.analytic.line";
export const TIMER_TIMER_DOMAIN: Domain = [
  ["timer_start", "!=", false],
  ["timer_pause", "=", false],
];
export const TIMER_TIMER_FIELDS = [
  "timer_start",
  "res_model",
  "res_id",
] as const;
const BASE_FIELDS = [
  "name",
  "project_id",
  "task_id",
  "unit_amount",
  "timer_start",
  "date",
] as const;

export enum TimerState {
  Running = "running",
  Stopped = "stopped",
}

export type TimerSourceKind = "task" | "ticket" | "standalone";

export class TimerSource {
  constructor(
    readonly kind: TimerSourceKind,
    readonly id: number,
    readonly name: string,
  ) {}

  get icon(): string {
    return { task: "🔧", ticket: "🎫", standalone: "⏱" }[this.kind];
  }

  get model(): string {
    return this.kind === "task"
      ? "project.task"
      : this.kind === "ticket"
        ? "helpdesk.ticket"
        : TIMESHEET_MODEL;
  }
}

export interface TimesheetObject {
  readonly id: number;
  readonly name: string;
  readonly projectName: string | null;
  readonly source: { kind: TimerSourceKind; id: number; name: string };
  readonly unitAmount: number;
  readonly state: TimerState;
  readonly elapsed: string;
  readonly date: Date;
}

export class Timesheet {
  constructor(
    readonly id: number,
    readonly name: string,
    readonly projectName: string | null,
    readonly source: TimerSource,
    readonly unitAmount: number,
    readonly timerStart: Date | null,
    readonly date: Date,
  ) {}

  get state(): TimerState {
    return this.timerStart === null ? TimerState.Stopped : TimerState.Running;
  }

  elapsedMilliseconds(now = new Date()): number {
    const base = this.unitAmount * 3_600_000;
    return this.timerStart === null
      ? base
      : base + now.getTime() - this.timerStart.getTime();
  }

  elapsedFormatted(now = new Date()): string {
    const totalSeconds = Math.trunc(this.elapsedMilliseconds(now) / 1000);
    const hours = Math.trunc(totalSeconds / 3600);
    const minutes = Math.trunc((totalSeconds % 3600) / 60);
    return `${hours}:${String(minutes).padStart(2, "0")}`;
  }

  get displayLabel(): string {
    const label =
      this.source.kind === "standalone"
        ? this.name || "Timesheet"
        : this.source.name;
    return `${this.source.icon} ${label}`;
  }

  toObject(now = new Date()): TimesheetObject {
    return {
      id: this.id,
      name: this.name,
      projectName: this.projectName,
      source: {
        kind: this.source.kind,
        id: this.source.id,
        name: this.source.name,
      },
      unitAmount: this.unitAmount,
      state: this.state,
      elapsed: this.elapsedFormatted(now),
      date: this.date,
    };
  }
}

export class TimerHandle {
  constructor(
    private readonly namespace: TimerNamespace,
    private readonly sourceKind: TimerSourceKind,
    private readonly sourceId: number,
  ) {}

  async stop(): Promise<void> {
    const active = await this.namespace.active();
    const timesheet = active.find(
      (candidate) =>
        candidate.source.kind === this.sourceKind &&
        candidate.source.id === this.sourceId,
    );
    if (timesheet !== undefined) {
      await this.namespace.stopOne(timesheet);
      return;
    }
    if (this.sourceKind === "standalone") {
      await this.namespace.stopTimesheet(this.sourceId);
      return;
    }
    throw new VodooError(
      `No running timer found for ${this.sourceKind} ${this.sourceId}`,
    );
  }
}

interface TimerBackend {
  enrichWithRunningState(
    timesheets: Timesheet[],
    uid: number,
  ): Promise<Timesheet[]>;
  startTimer(timesheet: Timesheet): Promise<void>;
  stopTimer(timesheet: Timesheet): Promise<unknown>;
}

function many2One(value: unknown): readonly [number, string] | null {
  return Array.isArray(value) &&
    typeof value[0] === "number" &&
    typeof value[1] === "string"
    ? [value[0], value[1]]
    : null;
}

function parseTimerDateTime(value: unknown): Date | null {
  if (typeof value !== "string") return null;
  try {
    return parseOdooDateTime(value);
  } catch {
    return null;
  }
}

function parseTimerDate(value: unknown): Date | null {
  if (typeof value !== "string") return null;
  try {
    return parseOdooDate(value);
  } catch {
    return null;
  }
}

function parseSource(record: OdooRecord): TimerSource {
  const task = many2One(record.task_id);
  if (task !== null) return new TimerSource("task", task[0], task[1]);
  const ticket = many2One(record.helpdesk_ticket_id);
  if (ticket !== null) return new TimerSource("ticket", ticket[0], ticket[1]);
  return new TimerSource("standalone", 0, "");
}

export function parseTimesheet(record: OdooRecord): Timesheet | null {
  if (typeof record.id !== "number") return null;
  const date = parseTimerDate(record.date);
  if (date === null) return null;
  const project = many2One(record.project_id);
  return new Timesheet(
    record.id,
    typeof record.name === "string" ? record.name : "",
    project?.[1] ?? null,
    parseSource(record),
    typeof record.unit_amount === "number" ? record.unit_amount : 0,
    parseTimerDateTime(record.timer_start),
    date,
  );
}

export function buildRunningTimer(
  record: OdooRecord,
  source: TimerSource,
  projectName: string | null,
  timerStart: Date,
  today = new Date(),
): Timesheet {
  const sourceRecordId = typeof record.id === "number" ? record.id : source.id;
  return new Timesheet(
    -sourceRecordId,
    "",
    projectName,
    source,
    0,
    timerStart,
    parseOdooDate(formatOdooDate(today)),
  );
}

export function mergeRunningTimers(
  timesheets: readonly Timesheet[],
  runningTimers: readonly Timesheet[],
): Timesheet[] {
  const result = [...timesheets];
  for (const timer of runningTimers) {
    const index = result.findIndex(
      (candidate) =>
        candidate.source.kind === timer.source.kind &&
        candidate.source.id === timer.source.id,
    );
    if (index === -1) {
      result.push(timer);
      continue;
    }
    const existing = result[index];
    if (existing === undefined) continue;
    result[index] = new Timesheet(
      existing.id,
      existing.name,
      existing.projectName,
      existing.source,
      existing.unitAmount,
      timer.timerStart,
      existing.date,
    );
  }
  return result;
}

function timerTarget(timesheet: Timesheet): readonly [string, number] {
  return timesheet.source.kind === "standalone"
    ? [TIMESHEET_MODEL, timesheet.id]
    : [timesheet.source.model, timesheet.source.id];
}

class Odoo19TimerBackend implements TimerBackend {
  constructor(private readonly client: OdooClientApi) {}

  async enrichWithRunningState(timesheets: Timesheet[]): Promise<Timesheet[]> {
    return timesheets;
  }

  async startTimer(timesheet: Timesheet): Promise<void> {
    await this.client.execute(TIMESHEET_MODEL, "action_timer_start", [
      [timesheet.id],
    ]);
  }

  stopTimer(timesheet: Timesheet): Promise<unknown> {
    return this.client.execute(TIMESHEET_MODEL, "action_timer_stop", [
      [timesheet.id],
    ]);
  }
}

class LegacyTimerBackend implements TimerBackend {
  constructor(private readonly client: OdooClientApi) {}

  async enrichWithRunningState(
    timesheets: Timesheet[],
    uid: number,
  ): Promise<Timesheet[]> {
    return mergeRunningTimers(timesheets, await this.fetchRunningTimers(uid));
  }

  async startTimer(timesheet: Timesheet): Promise<void> {
    const [model, recordId] = timerTarget(timesheet);
    await this.client.execute(model, "action_timer_start", [[recordId]]);
  }

  async stopTimer(timesheet: Timesheet): Promise<unknown> {
    const [model, recordId] = timerTarget(timesheet);
    return this.client.execute(model, "action_timer_stop", [[recordId]]);
  }

  private async fetchRunningTimers(uid: number): Promise<Timesheet[]> {
    let records: OdooRecord[];
    try {
      records = await this.client.searchRead("timer.timer", {
        domain: [["user_id", "=", uid], ...TIMER_TIMER_DOMAIN],
        fields: TIMER_TIMER_FIELDS,
      });
    } catch {
      return [];
    }
    const result: Timesheet[] = [];
    for (const record of records) {
      if (
        typeof record.res_model !== "string" ||
        typeof record.res_id !== "number"
      ) {
        continue;
      }
      const timerStart = parseTimerDateTime(record.timer_start);
      if (timerStart === null) continue;
      if (record.res_model === "project.task") {
        let name = `Task #${record.res_id}`;
        let projectName: string | null = null;
        try {
          const tasks = await this.client.searchRead("project.task", {
            domain: [["id", "=", record.res_id]],
            fields: ["display_name", "project_id"],
            limit: 1,
          });
          if (typeof tasks[0]?.display_name === "string")
            name = tasks[0].display_name;
          projectName = many2One(tasks[0]?.project_id)?.[1] ?? null;
        } catch {
          // Keep stable fallback labels when the source cannot be read.
        }
        result.push(
          buildRunningTimer(
            record,
            new TimerSource("task", record.res_id, name),
            projectName,
            timerStart,
          ),
        );
      } else if (record.res_model === "helpdesk.ticket") {
        let name = `Ticket #${record.res_id}`;
        try {
          const tickets = await this.client.searchRead("helpdesk.ticket", {
            domain: [["id", "=", record.res_id]],
            fields: ["display_name"],
            limit: 1,
          });
          if (typeof tickets[0]?.display_name === "string")
            name = tickets[0].display_name;
        } catch {
          // Keep stable fallback labels when the source cannot be read.
        }
        result.push(
          buildRunningTimer(
            record,
            new TimerSource("ticket", record.res_id, name),
            null,
            timerStart,
          ),
        );
      }
    }
    return result;
  }
}

interface StopWizard {
  readonly model: string;
  readonly values: Readonly<Record<string, unknown>>;
  readonly method: string;
  readonly context: Readonly<Record<string, unknown>>;
}

function stopWizard(result: unknown): StopWizard | null {
  if (typeof result !== "object" || result === null) return null;
  const action = result as Record<string, unknown>;
  if (
    action.type !== "ir.actions.act_window" ||
    typeof action.res_model !== "string"
  ) {
    return null;
  }
  const context =
    typeof action.context === "object" && action.context !== null
      ? (action.context as Readonly<Record<string, unknown>>)
      : {};
  if (action.res_model === "project.task.create.timesheet") {
    return {
      model: action.res_model,
      values: {
        task_id: context.active_id ?? 0,
        description: "/",
        time_spent: context.default_time_spent ?? 0,
      },
      method: "save_timesheet",
      context,
    };
  }
  if (action.res_model === "helpdesk.ticket.create.timesheet") {
    return {
      model: action.res_model,
      values: {
        ticket_id: context.active_id ?? 0,
        description: "/",
        time_spent: context.default_time_spent ?? 0,
      },
      method: "action_generate_timesheet",
      context,
    };
  }
  if (action.res_model === "hr.timesheet.stop.timer.confirmation.wizard") {
    return {
      model: action.res_model,
      values: { timesheet_id: context.default_timesheet_id ?? 0 },
      method: "action_stop_timer",
      context,
    };
  }
  return null;
}

export interface TimerListOptions {
  days?: number;
  limit?: number | null;
}

export class TimerNamespace {
  private helpdeskField: boolean | undefined;

  constructor(private readonly client: OdooClientApi) {}

  async list(options: TimerListOptions = {}): Promise<Timesheet[]> {
    const uid = await this.client.getUid();
    const fields = await this.fields();
    const days = options.days ?? 0;
    const domain: Array<Domain[number]> = [["user_id", "=", uid]];
    if (days >= 0) {
      domain.push([
        "date",
        ">=",
        formatOdooDate(new Date(Date.now() - days * 86_400_000)),
      ]);
    }
    const records = await this.client.searchRead(TIMESHEET_MODEL, {
      domain,
      fields,
      order: "date desc",
      limit: options.limit ?? null,
    });
    const timesheets = records
      .map(parseTimesheet)
      .filter((timesheet): timesheet is Timesheet => timesheet !== null);
    return this.backend().enrichWithRunningState(timesheets, uid);
  }

  async active(): Promise<Timesheet[]> {
    const uid = await this.client.getUid();
    if (!this.client.isJson2) {
      return (await this.list()).filter(
        (timesheet) => timesheet.timerStart !== null,
      );
    }
    const records = await this.client.searchRead(TIMESHEET_MODEL, {
      domain: [
        ["user_id", "=", uid],
        ["timer_start", "!=", false],
      ],
      fields: await this.fields(),
      order: "date desc",
    });
    return records
      .map(parseTimesheet)
      .filter(
        (timesheet): timesheet is Timesheet =>
          timesheet !== null && timesheet.timerStart !== null,
      );
  }

  async startTask(taskId: number): Promise<TimerHandle> {
    await this.client.execute("project.task", "action_timer_start", [[taskId]]);
    return new TimerHandle(this, "task", taskId);
  }

  async startTicket(ticketId: number): Promise<TimerHandle> {
    await this.client.execute("helpdesk.ticket", "action_timer_start", [
      [ticketId],
    ]);
    return new TimerHandle(this, "ticket", ticketId);
  }

  async startTimesheet(timesheetId: number): Promise<TimerHandle> {
    const timesheet = await this.loadTimesheet(timesheetId);
    await this.backend().startTimer(timesheet);
    const sourceId =
      timesheet.source.kind === "standalone"
        ? timesheetId
        : timesheet.source.id;
    return new TimerHandle(this, timesheet.source.kind, sourceId);
  }

  async stopTimesheet(timesheetId: number): Promise<void> {
    const timesheet = await this.loadTimesheet(timesheetId);
    await this.handleStopWizard(await this.backend().stopTimer(timesheet));
  }

  async stopOne(timesheet: Timesheet): Promise<void> {
    await this.client.getUid();
    await this.handleStopWizard(await this.backend().stopTimer(timesheet));
  }

  async stop(): Promise<Timesheet[]> {
    const active = await this.active();
    const backend = this.backend();
    for (const timesheet of active) {
      await this.handleStopWizard(await backend.stopTimer(timesheet));
    }
    return active;
  }

  private backend(): TimerBackend {
    return this.client.isJson2
      ? new Odoo19TimerBackend(this.client)
      : new LegacyTimerBackend(this.client);
  }

  private async hasHelpdeskField(): Promise<boolean> {
    if (this.helpdeskField !== undefined) return this.helpdeskField;
    try {
      await this.client.searchRead(TIMESHEET_MODEL, {
        domain: [],
        fields: ["id", "helpdesk_ticket_id"],
        limit: 1,
      });
      this.helpdeskField = true;
    } catch {
      this.helpdeskField = false;
    }
    return this.helpdeskField;
  }

  private async fields(): Promise<string[]> {
    const fields: string[] = [...BASE_FIELDS];
    if (await this.hasHelpdeskField()) fields.push("helpdesk_ticket_id");
    return fields;
  }

  private async loadTimesheet(timesheetId: number): Promise<Timesheet> {
    const records = await this.client.searchRead(TIMESHEET_MODEL, {
      domain: [["id", "=", timesheetId]],
      fields: await this.fields(),
      limit: 1,
    });
    if (records[0] === undefined)
      throw new VodooError(`Timesheet ${timesheetId} not found`);
    const timesheet = parseTimesheet(records[0]);
    if (timesheet === null)
      throw new VodooError(`Failed to parse timesheet ${timesheetId}`);
    return timesheet;
  }

  private async handleStopWizard(result: unknown): Promise<void> {
    const wizard = stopWizard(result);
    if (wizard === null) return;
    const wizardId = await this.client.create(wizard.model, wizard.values);
    await this.client.execute(wizard.model, wizard.method, [[wizardId]], {
      context: wizard.context,
    });
  }
}
