public struct CreateTicketOptions: Sendable {
    public var description: String?
    public var partnerID: Int?
    public var tagIDs: [Int]?
    public var teamID: Int?
    public var extraFields: OdooRecord

    public init(
        description: String? = nil,
        partnerID: Int? = nil,
        tagIDs: [Int]? = nil,
        teamID: Int? = nil,
        extraFields: OdooRecord = [:]
    ) {
        self.description = description
        self.partnerID = partnerID
        self.tagIDs = tagIDs
        self.teamID = teamID
        self.extraFields = extraFields
    }
}

public extension GeneratedHelpdeskNamespace {
    func create(_ name: String, options: CreateTicketOptions = CreateTicketOptions()) async throws -> Int {
        var values = options.extraFields
        values["name"] = .string(name)
        if let description = options.description { values["description"] = .string(description) }
        if let partnerID = options.partnerID { values["partner_id"] = .integer(partnerID) }
        if let tagIDs = options.tagIDs { values["tag_ids"] = .array([Command.set(tagIDs).wireValue]) }
        if let teamID = options.teamID { values["team_id"] = .integer(teamID) }
        return try await client.create(model: model, values: values, context: nil)
    }
}
