import Foundation

public struct ActivityDomainOptions: Sendable, Equatable {
    public var model: String?
    public var user: String?
    public var activityType: String?

    public init(model: String? = nil, user: String? = nil, activityType: String? = nil) {
        self.model = model
        self.user = user
        self.activityType = activityType
    }
}

public func buildActivityDomain(_ options: ActivityDomainOptions = ActivityDomainOptions()) -> Domain {
    var domain: Domain = []
    if let model = options.model, !model.isEmpty {
        domain.append(.array([.string("res_model"), .string("="), .string(model)]))
    }
    if let user = options.user, !user.isEmpty {
        domain.append(.array([.string("user_id.name"), .string("ilike"), .string(user)]))
    }
    if let activityType = options.activityType, !activityType.isEmpty {
        domain.append(.array([
            .string("activity_type_id.name"), .string("ilike"), .string(activityType),
        ]))
    }
    return domain
}

public extension GeneratedActivityNamespace {
    func done(_ activityID: Int) async throws -> JSONValue {
        let activity = try await get(activityID, fields: ["active"])
        guard activity["active"]?.boolValue == true else {
            throw VodooError.operation("Activity \(activityID) is already done")
        }
        return try await client.execute(
            model: "mail.activity", method: "action_done", args: [.array([.integer(activityID)])], kwargs: nil
        )
    }
}

public struct AccountMoveDomainOptions: Sendable, Equatable {
    public var search: String?
    public var company: String?
    public var companyID: Int?
    public var partner: String?
    public var moveType: String?
    public var state: String?
    public var year: Int?

    public init(
        search: String? = nil, company: String? = nil, companyID: Int? = nil,
        partner: String? = nil, moveType: String? = nil, state: String? = nil, year: Int? = nil
    ) {
        self.search = search
        self.company = company
        self.companyID = companyID
        self.partner = partner
        self.moveType = moveType
        self.state = state
        self.year = year
    }
}

public func buildAccountMoveDomain(
    _ options: AccountMoveDomainOptions = AccountMoveDomainOptions()
) -> Domain {
    var domain: Domain = []
    if let search = options.search, !search.isEmpty {
        domain.append(contentsOf: [.string("|"), .string("|"), .string("|")])
        for field in ["name", "ref", "payment_reference", "invoice_origin"] {
            domain.append(.array([.string(field), .string("ilike"), .string(search)]))
        }
    }
    if let company = options.company, !company.isEmpty {
        domain.append(.array([.string("company_id.name"), .string("ilike"), .string(company)]))
    }
    if let companyID = options.companyID {
        domain.append(.array([.string("company_id"), .string("="), .integer(companyID)]))
    }
    if let partner = options.partner, !partner.isEmpty {
        domain.append(.array([.string("partner_id.name"), .string("ilike"), .string(partner)]))
    }
    if let moveType = options.moveType, !moveType.isEmpty {
        domain.append(.array([.string("move_type"), .string("="), .string(moveType)]))
    }
    if let state = options.state, !state.isEmpty {
        domain.append(.array([.string("state"), .string("="), .string(state)]))
    }
    if let year = options.year {
        let text = String(format: "%04d", year)
        domain.append(.array([.string("date"), .string(">="), .string("\(text)-01-01")]))
        domain.append(.array([.string("date"), .string("<="), .string("\(text)-12-31")]))
    }
    return domain
}
