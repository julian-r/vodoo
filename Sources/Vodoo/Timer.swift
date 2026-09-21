import Foundation

public let timesheetModel = "account.analytic.line"
public let timerTimerDomain: Domain = [
    .array([.string("timer_start"), .string("!="), .bool(false)]),
    .array([.string("timer_pause"), .string("="), .bool(false)]),
]

public enum TimerState: String, Sendable, Equatable { case running, stopped }
public enum TimerSourceKind: String, Sendable, Equatable { case task, ticket, standalone }

public struct TimerSource: Sendable, Equatable {
    public let kind: TimerSourceKind
    public let id: Int
    public let name: String

    public init(kind: TimerSourceKind, id: Int, name: String) {
        self.kind = kind
        self.id = id
        self.name = name
    }

    public var icon: String {
        switch kind { case .task: "🔧"; case .ticket: "🎫"; case .standalone: "⏱" }
    }

    public var model: String {
        switch kind {
        case .task: "project.task"
        case .ticket: "helpdesk.ticket"
        case .standalone: timesheetModel
        }
    }
}

public struct Timesheet: Sendable, Equatable {
    public let id: Int
    public let name: String
    public let projectName: String?
    public let source: TimerSource
    public let unitAmount: Double
    public let timerStart: Date?
    public let date: Date

    public init(
        id: Int, name: String, projectName: String?, source: TimerSource,
        unitAmount: Double, timerStart: Date?, date: Date
    ) {
        self.id = id
        self.name = name
        self.projectName = projectName
        self.source = source
        self.unitAmount = unitAmount
        self.timerStart = timerStart
        self.date = date
    }

    public var state: TimerState { timerStart == nil ? .stopped : .running }

    public func elapsed(now: Date = Date()) -> TimeInterval {
        unitAmount * 3_600 + (timerStart.map { now.timeIntervalSince($0) } ?? 0)
    }

    public func elapsedFormatted(now: Date = Date()) -> String {
        let total = Int(elapsed(now: now))
        return String(format: "%d:%02d", total / 3_600, (total % 3_600) / 60)
    }

    public var displayLabel: String {
        let label = source.kind == .standalone ? (name.isEmpty ? "Timesheet" : name) : source.name
        return "\(source.icon) \(label)"
    }
}

public final class TimerHandle: @unchecked Sendable {
    private let namespace: TimerNamespace
    private let sourceKind: TimerSourceKind
    private let sourceID: Int

    init(namespace: TimerNamespace, sourceKind: TimerSourceKind, sourceID: Int) {
        self.namespace = namespace
        self.sourceKind = sourceKind
        self.sourceID = sourceID
    }

    public func stop() async throws {
        if let timesheet = try await namespace.active().first(where: {
            $0.source.kind == sourceKind && $0.source.id == sourceID
        }) {
            try await namespace.stop(timesheet)
            return
        }
        if sourceKind == .standalone {
            try await namespace.stopTimesheet(sourceID)
            return
        }
        throw VodooError.operation("No running timer found for \(sourceKind.rawValue) \(sourceID)")
    }
}

public final class TimerNamespace: @unchecked Sendable {
    private let client: any OdooClientAPI
    private var helpdeskField: Bool?

    public init(client: any OdooClientAPI) { self.client = client }

    public func list(days: Int = 0, limit: Int? = nil) async throws -> [Timesheet] {
        let uid = try await client.getUID()
        var domain: Domain = [
            .array([.string("user_id"), .string("="), .integer(uid)]),
        ]
        if days >= 0 {
            domain.append(.array([
                .string("date"), .string(">="),
                .string(try OdooDateCodec.formatDate(Date().addingTimeInterval(Double(-days) * 86_400))),
            ]))
        }
        let records = try await client.searchRead(
            model: timesheetModel, domain: domain, fields: await fields(),
            limit: limit, offset: 0, order: "date desc"
        )
        let timesheets = records.compactMap(parseTimesheet)
        if try await client.transportDialect() == .json2 { return timesheets }
        return mergeRunningTimers(timesheets, try await fetchRunningTimers(uid: uid))
    }

    public func active() async throws -> [Timesheet] {
        let days = try await client.transportDialect() == .json2 ? -1 : 0
        return try await list(days: days).filter { $0.timerStart != nil }
    }

    public func startTask(_ taskID: Int) async throws -> TimerHandle {
        _ = try await client.execute(
            model: "project.task", method: "action_timer_start",
            args: [.array([.integer(taskID)])], kwargs: nil
        )
        return TimerHandle(namespace: self, sourceKind: .task, sourceID: taskID)
    }

    public func startTicket(_ ticketID: Int) async throws -> TimerHandle {
        _ = try await client.execute(
            model: "helpdesk.ticket", method: "action_timer_start",
            args: [.array([.integer(ticketID)])], kwargs: nil
        )
        return TimerHandle(namespace: self, sourceKind: .ticket, sourceID: ticketID)
    }

    public func startTimesheet(_ timesheetID: Int) async throws -> TimerHandle {
        let timesheet = try await loadTimesheet(timesheetID)
        if try await client.transportDialect() == .json2 {
            _ = try await client.execute(
                model: timesheetModel, method: "action_timer_start",
                args: [.array([.integer(timesheet.id)])], kwargs: nil
            )
        } else {
            let target = timerTarget(timesheet)
            _ = try await client.execute(
                model: target.0, method: "action_timer_start",
                args: [.array([.integer(target.1)])], kwargs: nil
            )
        }
        let sourceID = timesheet.source.kind == .standalone ? timesheetID : timesheet.source.id
        return TimerHandle(namespace: self, sourceKind: timesheet.source.kind, sourceID: sourceID)
    }

    public func stopTimesheet(_ timesheetID: Int) async throws {
        try await stop(loadTimesheet(timesheetID))
    }

    public func stop(_ timesheet: Timesheet) async throws {
        _ = try await client.getUID()
        let result: JSONValue
        if try await client.transportDialect() == .json2 {
            result = try await client.execute(
                model: timesheetModel, method: "action_timer_stop",
                args: [.array([.integer(timesheet.id)])], kwargs: nil
            )
        } else {
            let target = timerTarget(timesheet)
            result = try await client.execute(
                model: target.0, method: "action_timer_stop",
                args: [.array([.integer(target.1)])], kwargs: nil
            )
        }
        try await handleStopWizard(result)
    }

    @discardableResult
    public func stopAll() async throws -> [Timesheet] {
        let values = try await active()
        for timesheet in values { try await stop(timesheet) }
        return values
    }

    private func hasHelpdeskField() async -> Bool {
        if let helpdeskField { return helpdeskField }
        do {
            _ = try await client.searchRead(
                model: timesheetModel, domain: [], fields: ["id", "helpdesk_ticket_id"],
                limit: 1, offset: 0, order: nil
            )
            helpdeskField = true
        } catch {
            helpdeskField = false
        }
        return helpdeskField ?? false
    }

    private func fields() async -> [String] {
        var values = ["name", "project_id", "task_id", "unit_amount", "timer_start", "date"]
        if await hasHelpdeskField() { values.append("helpdesk_ticket_id") }
        return values
    }

    private func loadTimesheet(_ id: Int) async throws -> Timesheet {
        let records = try await client.searchRead(
            model: timesheetModel,
            domain: [.array([.string("id"), .string("="), .integer(id)])],
            fields: await fields(), limit: 1, offset: 0, order: nil
        )
        guard let record = records.first else { throw VodooError.operation("Timesheet \(id) not found") }
        guard let result = parseTimesheet(record) else {
            throw VodooError.operation("Failed to parse timesheet \(id)")
        }
        return result
    }

    private func fetchRunningTimers(uid: Int) async throws -> [Timesheet] {
        let records: [OdooRecord]
        do {
            records = try await client.searchRead(
                model: "timer.timer",
                domain: [.array([.string("user_id"), .string("="), .integer(uid)])] + timerTimerDomain,
                fields: ["timer_start", "res_model", "res_id"],
                limit: nil, offset: 0, order: nil
            )
        } catch { return [] }
        var result: [Timesheet] = []
        for record in records {
            guard let model = record["res_model"]?.stringValue,
                  let id = record["res_id"]?.intValue,
                  let startText = record["timer_start"]?.stringValue,
                  let timerStart = try? OdooDateCodec.parseDateTime(startText) else { continue }
            if model == "project.task" {
                var name = "Task #\(id)"
                var project: String?
                if let task = try? await client.searchRead(
                    model: model,
                    domain: [.array([.string("id"), .string("="), .integer(id)])],
                    fields: ["display_name", "project_id"], limit: 1, offset: 0, order: nil
                ).first {
                    name = task["display_name"]?.stringValue ?? name
                    project = relationName(task["project_id"])
                }
                result.append(buildRunningTimer(
                    record: record, source: TimerSource(kind: .task, id: id, name: name),
                    projectName: project, timerStart: timerStart
                ))
            } else if model == "helpdesk.ticket" {
                var name = "Ticket #\(id)"
                if let ticket = try? await client.searchRead(
                    model: model,
                    domain: [.array([.string("id"), .string("="), .integer(id)])],
                    fields: ["display_name"], limit: 1, offset: 0, order: nil
                ).first {
                    name = ticket["display_name"]?.stringValue ?? name
                }
                result.append(buildRunningTimer(
                    record: record, source: TimerSource(kind: .ticket, id: id, name: name),
                    projectName: nil, timerStart: timerStart
                ))
            }
        }
        return result
    }

    private func handleStopWizard(_ result: JSONValue) async throws {
        guard let action = result.objectValue,
              action["type"]?.stringValue == "ir.actions.act_window",
              let model = action["res_model"]?.stringValue else { return }
        let context = action["context"]?.objectValue ?? [:]
        let values: OdooRecord
        let method: String
        switch model {
        case "project.task.create.timesheet":
            values = [
                "task_id": context["active_id"] ?? .integer(0),
                "description": .string("/"),
                "time_spent": context["default_time_spent"] ?? .integer(0),
            ]
            method = "save_timesheet"
        case "helpdesk.ticket.create.timesheet":
            values = [
                "ticket_id": context["active_id"] ?? .integer(0),
                "description": .string("/"),
                "time_spent": context["default_time_spent"] ?? .integer(0),
            ]
            method = "action_generate_timesheet"
        case "hr.timesheet.stop.timer.confirmation.wizard":
            values = ["timesheet_id": context["default_timesheet_id"] ?? .integer(0)]
            method = "action_stop_timer"
        default: return
        }
        let wizardID = try await client.create(model: model, values: values, context: nil)
        _ = try await client.execute(
            model: model, method: method, args: [.array([.integer(wizardID)])],
            kwargs: ["context": .object(context)]
        )
    }
}

public func parseTimesheet(_ record: OdooRecord) -> Timesheet? {
    guard let id = record["id"]?.intValue,
          let dateText = record["date"]?.stringValue,
          let date = try? OdooDateCodec.parseDate(dateText) else { return nil }
    let source: TimerSource
    if let task = relationID(record["task_id"]) {
        source = TimerSource(kind: .task, id: task, name: relationName(record["task_id"]) ?? "")
    } else if let ticket = relationID(record["helpdesk_ticket_id"]) {
        source = TimerSource(
            kind: .ticket, id: ticket, name: relationName(record["helpdesk_ticket_id"]) ?? ""
        )
    } else {
        source = TimerSource(kind: .standalone, id: 0, name: "")
    }
    let timerStart = record["timer_start"]?.stringValue.flatMap { try? OdooDateCodec.parseDateTime($0) }
    return Timesheet(
        id: id, name: record["name"]?.stringValue ?? "",
        projectName: relationName(record["project_id"]), source: source,
        unitAmount: record["unit_amount"]?.doubleValue ?? 0,
        timerStart: timerStart, date: date
    )
}

public func buildRunningTimer(
    record: OdooRecord,
    source: TimerSource,
    projectName: String?,
    timerStart: Date,
    today: Date = Date()
) -> Timesheet {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    return Timesheet(
        id: -(record["id"]?.intValue ?? source.id), name: "", projectName: projectName,
        source: source, unitAmount: 0, timerStart: timerStart, date: calendar.startOfDay(for: today)
    )
}

public func mergeRunningTimers(_ timesheets: [Timesheet], _ running: [Timesheet]) -> [Timesheet] {
    var result = timesheets
    for timer in running {
        if let index = result.firstIndex(where: {
            $0.source.kind == timer.source.kind && $0.source.id == timer.source.id
        }) {
            let current = result[index]
            result[index] = Timesheet(
                id: current.id, name: current.name, projectName: current.projectName,
                source: current.source, unitAmount: current.unitAmount,
                timerStart: timer.timerStart, date: current.date
            )
        } else {
            result.append(timer)
        }
    }
    return result
}

private func timerTarget(_ timesheet: Timesheet) -> (String, Int) {
    timesheet.source.kind == .standalone
        ? (timesheetModel, timesheet.id) : (timesheet.source.model, timesheet.source.id)
}
