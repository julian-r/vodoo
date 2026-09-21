import Foundation

public struct CreateCRMOptions: Sendable, Equatable {
    public var partnerID: Int?
    public var expectedRevenue: Double?
    public var stageID: Int?
    public var userID: Int?
    public var teamID: Int?
    public var tagIDs: [Int]?
    public var leadType: String
    public var extraFields: OdooRecord

    public init(
        partnerID: Int? = nil, expectedRevenue: Double? = nil, stageID: Int? = nil,
        userID: Int? = nil, teamID: Int? = nil, tagIDs: [Int]? = nil,
        leadType: String = "opportunity", extraFields: OdooRecord = [:]
    ) {
        self.partnerID = partnerID
        self.expectedRevenue = expectedRevenue
        self.stageID = stageID
        self.userID = userID
        self.teamID = teamID
        self.tagIDs = tagIDs
        self.leadType = leadType
        self.extraFields = extraFields
    }
}

public struct PipelineStageSummary: Sendable, Equatable {
    public let stageID: Int
    public let name: String
    public let deals: Int
    public let revenue: Double
    public let weighted: Double
    public let averageAgeDays: Int
    public let oldestDays: Int
}

public struct PipelineDeal: Sendable, Equatable {
    public let id: Int
    public let name: String
    public let stageID: Int?
    public let stageName: String
    public let expectedRevenue: Double
    public let probability: Double
    public let ageDays: Int
    public let partner: String?
    public let user: String?
    public let stageOrder: Int
}

public struct PipelineTotals: Sendable, Equatable {
    public let deals: Int
    public let revenue: Double
    public let weighted: Double
}

public struct PipelineSummary: Sendable, Equatable {
    public let team: String
    public let date: String
    public let stages: [PipelineStageSummary]
    public let totals: PipelineTotals
    public let deals: [PipelineDeal]
}

public enum HealthSeverity: Int, Sendable, Equatable { case critical, warning, info }

public struct HealthFlag: Sendable, Equatable {
    public let severity: HealthSeverity
    public let rule: String
    public let dealID: Int
    public let dealName: String
    public let detail: String
}

public struct StaleThresholds: Sendable, Equatable {
    public var first: Int
    public var middle: Int
    public var late: Int
    public init(first: Int = 30, middle: Int = 45, late: Int = 60) {
        self.first = first
        self.middle = middle
        self.late = late
    }
}

public extension GeneratedCRMNamespace {
    func create(_ name: String, options: CreateCRMOptions = CreateCRMOptions()) async throws -> Int {
        var values = options.extraFields
        values["name"] = .string(name)
        values["type"] = .string(options.leadType)
        if let id = options.partnerID { values["partner_id"] = .integer(id) }
        if let value = options.expectedRevenue { values["expected_revenue"] = .number(value) }
        if let id = options.stageID { values["stage_id"] = .integer(id) }
        if let id = options.userID { values["user_id"] = .integer(id) }
        if let id = options.teamID { values["team_id"] = .integer(id) }
        if let ids = options.tagIDs { values["tag_ids"] = .array([Command.set(ids).wireValue]) }
        return try await client.create(model: model, values: values, context: nil)
    }

    func pipeline(team: String? = nil, user: String? = nil) async throws -> PipelineSummary {
        var domain: Domain = [.array([.string("type"), .string("="), .string("opportunity")])]
        if let team, !team.isEmpty {
            domain.append(.array([.string("team_id.name"), .string("ilike"), .string(team)]))
        }
        if let user, !user.isEmpty {
            domain.append(.array([.string("user_id.name"), .string("ilike"), .string(user)]))
        }
        let deals = try await client.searchRead(
            model: model,
            domain: domain,
            fields: [
                "id", "name", "stage_id", "expected_revenue", "probability", "create_date",
                "partner_id", "user_id", "team_id",
            ],
            limit: 0,
            offset: 0,
            order: nil
        )
        let stages = try await client.searchRead(
            model: "crm.stage",
            domain: [],
            fields: ["id", "name", "sequence", "is_won", "fold"],
            limit: nil,
            offset: 0,
            order: "sequence"
        )
        return try buildPipelineSummary(deals: deals, stages: stages, team: team)
    }
}

public func buildPipelineSummary(
    deals: [OdooRecord],
    stages: [OdooRecord],
    team: String? = nil,
    today: Date = Date()
) throws -> PipelineSummary {
    var stageOrder: [Int: Int] = [:]
    var stageNames: [Int: String] = [:]
    for (index, stage) in stages.enumerated() {
        guard let id = stage["id"]?.intValue else { continue }
        stageOrder[id] = index
        stageNames[id] = stage["name"]?.stringValue ?? "Stage \(id)"
    }
    var byStage: [Int: [OdooRecord]] = [:]
    for deal in deals {
        guard let id = relationID(deal["stage_id"]) else { continue }
        byStage[id, default: []].append(deal)
    }

    var summaries: [PipelineStageSummary] = []
    var totalDeals = 0
    var totalRevenue = 0.0
    var totalWeighted = 0.0
    for stage in stages {
        guard let id = stage["id"]?.intValue else { continue }
        let matches = byStage[id] ?? []
        guard !matches.isEmpty else { continue }
        let revenue = matches.reduce(0) { $0 + ($1["expected_revenue"]?.doubleValue ?? 0) }
        let weighted = matches.reduce(0) {
            $0 + ($1["expected_revenue"]?.doubleValue ?? 0) * ($1["probability"]?.doubleValue ?? 0) / 100
        }
        let ages = matches.map { ageDays($0["create_date"]?.stringValue, today: today) }
        summaries.append(PipelineStageSummary(
            stageID: id,
            name: stageNames[id] ?? "Stage \(id)",
            deals: matches.count,
            revenue: revenue,
            weighted: roundedEven(weighted, digits: 2),
            averageAgeDays: Int((Double(ages.reduce(0, +)) / Double(matches.count)).rounded(.toNearestOrEven)),
            oldestDays: ages.max() ?? 0
        ))
        totalDeals += matches.count
        totalRevenue += revenue
        totalWeighted += weighted
    }

    let enriched = deals.compactMap { deal -> PipelineDeal? in
        guard let id = deal["id"]?.intValue else { return nil }
        let stageID = relationID(deal["stage_id"])
        return PipelineDeal(
            id: id,
            name: deal["name"]?.stringValue ?? "",
            stageID: stageID,
            stageName: stageID.flatMap { stageNames[$0] } ?? "",
            expectedRevenue: deal["expected_revenue"]?.doubleValue ?? 0,
            probability: deal["probability"]?.doubleValue ?? 0,
            ageDays: ageDays(deal["create_date"]?.stringValue, today: today),
            partner: relationName(deal["partner_id"]),
            user: relationName(deal["user_id"]),
            stageOrder: stageID.flatMap { stageOrder[$0] } ?? 999
        )
    }.sorted {
        $0.stageOrder == $1.stageOrder
            ? $0.expectedRevenue > $1.expectedRevenue
            : $0.stageOrder < $1.stageOrder
    }
    return PipelineSummary(
        team: team == nil || team == "" ? "All Teams" : team!,
        date: try OdooDateCodec.formatDate(today),
        stages: summaries,
        totals: PipelineTotals(
            deals: totalDeals, revenue: totalRevenue,
            weighted: roundedEven(totalWeighted, digits: 2)
        ),
        deals: enriched
    )
}

public func computeHealthFlags(
    _ summary: PipelineSummary,
    thresholds: StaleThresholds = StaleThresholds()
) -> [HealthFlag] {
    let positions = Dictionary(uniqueKeysWithValues: summary.stages.enumerated().map { ($1.stageID, $0) })
    var flags: [HealthFlag] = []
    for deal in summary.deals {
        let position = deal.stageID.flatMap { positions[$0] } ?? 0
        if deal.probability == 0 {
            flags.append(HealthFlag(
                severity: .critical, rule: "Zero probability", dealID: deal.id,
                dealName: deal.name, detail: "Open deal with 0% probability"
            ))
        }
        if deal.expectedRevenue == 0, position > 0 {
            flags.append(HealthFlag(
                severity: .warning, rule: "Missing revenue", dealID: deal.id,
                dealName: deal.name, detail: "No expected revenue in stage '\(deal.stageName)'"
            ))
        }
        let halfway = summary.stages.count / 2
        let threshold = position == 0
            ? thresholds.first : (position < halfway ? thresholds.middle : thresholds.late)
        if deal.ageDays > threshold {
            flags.append(HealthFlag(
                severity: position == 0 ? .info : .warning,
                rule: "Stale deal", dealID: deal.id, dealName: deal.name,
                detail: position == 0
                    ? "\(deal.ageDays)d in first stage (threshold: \(threshold)d)"
                    : "\(deal.ageDays)d in '\(deal.stageName)' (threshold: \(threshold)d)"
            ))
        }
        if deal.partner == nil {
            flags.append(HealthFlag(
                severity: .warning, rule: "No partner", dealID: deal.id,
                dealName: deal.name, detail: "No partner linked"
            ))
        }
        if deal.user == nil {
            flags.append(HealthFlag(
                severity: .warning, rule: "No salesperson", dealID: deal.id,
                dealName: deal.name, detail: "No salesperson assigned"
            ))
        }
    }
    return flags.sorted {
        $0.severity.rawValue == $1.severity.rawValue
            ? $0.dealName.localizedStandardCompare($1.dealName) == .orderedAscending
            : $0.severity.rawValue < $1.severity.rawValue
    }
}

private func roundedEven(_ value: Double, digits: Int) -> Double {
    guard value.isFinite, digits >= 0, digits <= 9 else { return value }
    let magnitude = abs(value)
    if magnitude == 0 { return value }
    let bits = magnitude.bitPattern
    let exponentBits = Int((bits >> 52) & 0x7ff)
    let fraction = bits & ((UInt64(1) << 52) - 1)
    let significand = exponentBits == 0 ? fraction : fraction | (UInt64(1) << 52)
    let binaryExponent = (exponentBits == 0 ? 1 - 1023 : exponentBits - 1023) - 52
    let factor = (0 ..< digits).reduce(UInt64(1)) { result, _ in result * 10 }
    let multiplied = significand.multipliedReportingOverflow(by: factor)
    guard !multiplied.overflow else {
        return (value * Double(factor)).rounded(.toNearestOrEven) / Double(factor)
    }
    var numerator = multiplied.partialValue
    var denominator = UInt64(1)
    if binaryExponent >= 0 {
        guard binaryExponent < 64, numerator <= UInt64.max >> binaryExponent else {
            return (value * Double(factor)).rounded(.toNearestOrEven) / Double(factor)
        }
        numerator <<= binaryExponent
    } else {
        let shift = -binaryExponent
        guard shift < 64 else { return 0 }
        denominator <<= shift
    }
    var quotient = numerator / denominator
    let remainder = numerator % denominator
    let half = denominator / 2
    if remainder > half || (remainder == half && quotient.isMultiple(of: 2) == false) {
        quotient += 1
    }
    let rounded = Double(quotient) / Double(factor)
    return value < 0 ? -rounded : rounded
}

private func ageDays(_ value: String?, today: Date) -> Int {
    guard let value, let created = try? OdooDateCodec.parseDateTime(value) else { return 0 }
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    let start = calendar.startOfDay(for: created)
    let end = calendar.startOfDay(for: today)
    return calendar.dateComponents([.day], from: start, to: end).day ?? 0
}
