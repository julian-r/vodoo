import Foundation

public func getDefaultUserID(
    client: any OdooClientAPI,
    username: String? = nil
) async throws -> Int {
    let login = username ?? client.username
    let ids = try await client.search(
        model: "res.users",
        domain: [.array([.string("login"), .string("="), .string(login)])],
        limit: 1, offset: 0, order: nil
    )
    guard let id = ids.first else { throw VodooError.recordNotFound(model: "res.users", id: 0) }
    return id
}

public func getPartnerIDFromUser(
    client: any OdooClientAPI,
    userID: Int
) async throws -> Int {
    let users = try await client.read(model: "res.users", ids: [userID], fields: ["partner_id"])
    guard let user = users.first else {
        throw VodooError.recordNotFound(model: "res.users", id: userID)
    }
    guard let partnerID = relationID(user["partner_id"]) else {
        throw VodooError.recordNotFound(model: "res.partner", id: 0)
    }
    return partnerID
}

public struct SudoMessageOptions: Sendable, Equatable {
    public var userID: Int?
    public var messageType: String
    public var isNote: Bool
    public var extraValues: OdooRecord

    public init(
        userID: Int? = nil,
        messageType: String = "comment",
        isNote: Bool = false,
        extraValues: OdooRecord = [:]
    ) {
        self.userID = userID
        self.messageType = messageType
        self.isNote = isNote
        self.extraValues = extraValues
    }
}

/// Creates a message requesting the selected user's partner as its displayed author.
/// Cross-user attribution requires an internal authenticated user. Odoo may reject or override
/// it for share users, which can reliably attribute only to their own partner. This does not
/// change authenticated identity, access checks, or auditing.
public func messagePostSudoWithID(
    client: any OdooClientAPI,
    model: String,
    recordID: Int,
    body: String,
    options: SudoMessageOptions = SudoMessageOptions()
) async throws -> Int {
    guard let userID = options.userID ?? client.defaultUserID else {
        throw VodooError.configuration("No default user ID configured")
    }
    let partnerID = try await getPartnerIDFromUser(client: client, userID: userID)
    let subtypeXMLID = options.isNote ? "mt_note" : "mt_comment"
    let subtypeRows = try await client.searchRead(
        model: "ir.model.data",
        domain: [
            .array([.string("module"), .string("="), .string("mail")]),
            .array([.string("name"), .string("="), .string(subtypeXMLID)]),
        ],
        fields: ["res_id"], limit: 1, offset: 0, order: nil
    )
    guard let subtypeID = subtypeRows.first?["res_id"]?.intValue, subtypeID > 0 else {
        throw VodooError.recordNotFound(model: "mail.message.subtype", id: 0)
    }
    var values = options.extraValues
    values["model"] = .string(model)
    values["res_id"] = .integer(recordID)
    values["body"] = .string(body)
    values["message_type"] = .string(options.isNote ? "notification" : options.messageType)
    values["subtype_id"] = .integer(subtypeID)
    values["author_id"] = .integer(partnerID)
    return try await client.create(model: "mail.message", values: values, context: nil)
}

/// Creates a message requesting selected-user author attribution.
/// Cross-user attribution requires an internal authenticated user. Odoo may reject or override
/// it for share users, which can reliably attribute only to their own partner. This does not
/// change authenticated identity, access checks, or auditing.
public func messagePostSudo(
    client: any OdooClientAPI,
    model: String,
    recordID: Int,
    body: String,
    options: SudoMessageOptions = SudoMessageOptions()
) async throws -> Bool {
    try await messagePostSudoWithID(
        client: client, model: model, recordID: recordID, body: body, options: options
    ) > 0
}
