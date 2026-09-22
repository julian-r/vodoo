import Foundation

public struct MessageOptions: Sendable, Equatable {
    public var userID: Int?
    public var markdown: Bool

    public init(userID: Int? = nil, markdown: Bool = true) {
        self.userID = userID
        self.markdown = markdown
    }
}

public struct AttachmentOptions: Sendable, Equatable {
    public var mimetype: String?
    public init(mimetype: String? = nil) { self.mimetype = mimetype }
}

public struct AttachmentData: Sendable, Equatable {
    public let id: Int
    public let name: String
    public let data: Data
    public let mimetype: String?

    public init(id: Int, name: String, data: Data, mimetype: String? = nil) {
        self.id = id
        self.name = name
        self.data = data
        self.mimetype = mimetype
    }
}

open class DomainNamespace: @unchecked Sendable {
    public let model: String
    public let defaultFields: [String]
    public let defaultDetailFields: [String]?
    public let tagModel: String?
    public let dateFields: [String: OdooDateKind]
    public let capabilities: [String]
    public let availability: NamespaceAvailability
    internal let client: any OdooClientAPI

    public init(
        client: any OdooClientAPI,
        model: String,
        defaultFields: [String],
        defaultDetailFields: [String]?,
        tagModel: String?,
        dateFields: [String: OdooDateKind] = [:],
        capabilities: [String],
        availability: NamespaceAvailability
    ) {
        self.client = client
        self.model = model
        self.defaultFields = defaultFields
        self.defaultDetailFields = defaultDetailFields
        self.tagModel = tagModel
        self.dateFields = dateFields
        self.capabilities = capabilities
        self.availability = availability
    }

    open func list(
        domain: Domain = [],
        limit: Int? = 50,
        fields: [String]? = nil,
        order: String = "create_date desc"
    ) async throws -> [OdooRecord] {
        let records = try await client.searchRead(
            model: model,
            domain: domain,
            fields: fields ?? defaultFields,
            limit: limit,
            offset: 0,
            order: order
        )
        return try records.map { try decodeRecordDates($0, fields: dateFields) }
    }

    open func get(_ recordID: Int, fields: [String]? = nil) async throws -> OdooRecord {
        let records = try await client.read(
            model: model,
            ids: [recordID],
            fields: fields ?? defaultDetailFields
        )
        guard let record = records.first else {
            throw VodooError.recordNotFound(model: model, id: recordID)
        }
        return try decodeRecordDates(record, fields: dateFields)
    }

    public func set(_ recordID: Int, values: OdooRecord) async throws -> Bool {
        try await client.write(model: model, ids: [recordID], values: values)
    }

    public func fields() async throws -> OdooRecord {
        try await client.fieldsGet(model: model, fields: nil, attributes: nil)
    }

    public func comment(
        _ recordID: Int,
        message: RichText,
        options: MessageOptions = MessageOptions()
    ) async throws -> Bool {
        try await commentWithID(recordID, message: message, options: options) > 0
    }

    public func commentWithID(
        _ recordID: Int,
        message: RichText,
        options: MessageOptions = MessageOptions()
    ) async throws -> Int {
        try await postMessage(recordID, message: message, isNote: false, options: options)
    }

    public func note(
        _ recordID: Int,
        message: RichText,
        options: MessageOptions = MessageOptions()
    ) async throws -> Bool {
        try await noteWithID(recordID, message: message, options: options) > 0
    }

    public func noteWithID(
        _ recordID: Int,
        message: RichText,
        options: MessageOptions = MessageOptions()
    ) async throws -> Int {
        try await postMessage(recordID, message: message, isNote: true, options: options)
    }

    public func messages(_ recordID: Int, limit: Int? = nil) async throws -> [OdooRecord] {
        let records = try await client.searchRead(
            model: "mail.message",
            domain: [
                .array([.string("model"), .string("="), .string(model)]),
                .array([.string("res_id"), .string("="), .integer(recordID)]),
            ],
            fields: [
                "id", "date", "author_id", "body", "subject", "message_type",
                "subtype_id", "email_from",
            ],
            limit: limit,
            offset: 0,
            order: "date desc"
        )
        return try records.map { try decodeRecordDates($0, fields: ["date": .dateTime]) }
    }

    public func tags() async throws -> [OdooRecord] {
        guard let tagModel else { throw VodooError.operation("No tag model defined for \(model)") }
        return try await client.searchRead(
            model: tagModel,
            domain: [],
            fields: ["id", "name", "color"],
            limit: nil,
            offset: 0,
            order: "name"
        )
    }

    public func addTag(_ recordID: Int, tagID: Int) async throws -> Bool {
        let record = try await get(recordID, fields: ["tag_ids"])
        let existing = record["tag_ids"]?.arrayValue?.compactMap(\.intValue) ?? []
        if existing.contains(tagID) { return true }
        return try await client.write(
            model: model,
            ids: [recordID],
            values: ["tag_ids": .array([Command.set(existing + [tagID]).wireValue])]
        )
    }

    public func attachments(_ recordID: Int) async throws -> [OdooRecord] {
        let records = try await client.searchRead(
            model: "ir.attachment",
            domain: [
                .array([.string("res_model"), .string("="), .string(model)]),
                .array([.string("res_id"), .string("="), .integer(recordID)]),
            ],
            fields: ["id", "name", "file_size", "mimetype", "create_date"],
            limit: nil,
            offset: 0,
            order: nil
        )
        return try records.map { try decodeRecordDates($0, fields: ["create_date": .dateTime]) }
    }

    public func attach(
        _ recordID: Int,
        data: Data,
        name: String,
        options: AttachmentOptions = AttachmentOptions()
    ) async throws -> Int {
        var values: OdooRecord = [
            "name": .string(name),
            "datas": .string(OdooBinaryCodec.encode(data)),
            "res_model": .string(model),
            "res_id": .integer(recordID),
            "type": .string("binary"),
        ]
        if let mimetype = options.mimetype { values["mimetype"] = .string(mimetype) }
        return try await client.create(model: "ir.attachment", values: values, context: nil)
    }

    public func attachmentData(_ attachmentID: Int) async throws -> Data {
        let records = try await client.read(
            model: "ir.attachment",
            ids: [attachmentID],
            fields: ["name", "datas", "file_size"]
        )
        guard let attachment = records.first else {
            throw VodooError.recordNotFound(model: "ir.attachment", id: attachmentID)
        }
        if let encoded = attachment["datas"]?.stringValue { return try OdooBinaryCodec.decode(encoded) }
        if attachment["file_size"]?.intValue == 0 { return Data() }
        throw VodooError.recordNotFound(model: "ir.attachment", id: attachmentID)
    }

    public func allAttachmentData(_ recordID: Int) async throws -> [AttachmentData] {
        let metadata = try await attachments(recordID)
        var result: [AttachmentData] = []
        for attachment in metadata {
            guard let id = attachment["id"]?.intValue else { continue }
            do {
                let records = try await client.read(
                    model: "ir.attachment",
                    ids: [id],
                    fields: ["id", "name", "datas", "file_size"]
                )
                guard let record = records.first else { continue }
                let data: Data
                if let encoded = record["datas"]?.stringValue {
                    data = try OdooBinaryCodec.decode(encoded)
                } else if record["file_size"]?.intValue == 0 {
                    data = Data()
                } else {
                    continue
                }
                result.append(AttachmentData(
                    id: id,
                    name: record["name"]?.stringValue ?? "attachment_\(id)",
                    data: data,
                    mimetype: attachment["mimetype"]?.stringValue
                ))
            } catch {
                continue
            }
        }
        return result
    }

    public func download(_ recordID: Int, extension requestedExtension: String? = nil) async throws
        -> [AttachmentData]
    {
        let values = try await allAttachmentData(recordID)
        guard let requestedExtension else { return values }
        let suffix = "." + requestedExtension.trimmingCharacters(in: CharacterSet(charactersIn: "."))
            .lowercased()
        return values.filter { $0.name.lowercased().hasSuffix(suffix) }
    }

    public func url(_ recordID: Int) -> URL {
        client.recordURL(model: model, recordID: recordID)
    }

    private func postMessage(
        _ recordID: Int,
        message: RichText,
        isNote: Bool,
        options: MessageOptions
    ) async throws -> Int {
        try await messagePostSudoWithID(
            client: client,
            model: model,
            recordID: recordID,
            body: OdooContent.richTextToHTML(message, markdownByDefault: options.markdown),
            options: SudoMessageOptions(userID: options.userID, isNote: isNote)
        )
    }
}

internal func relationID(_ value: JSONValue?) -> Int? {
    guard let value else { return nil }
    if let id = value.intValue { return id }
    return value.arrayValue?.first?.intValue
}

internal func relationName(_ value: JSONValue?) -> String? {
    value?.arrayValue.flatMap { $0.count > 1 ? $0[1].stringValue : nil }
}
