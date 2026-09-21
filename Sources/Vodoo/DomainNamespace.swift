import Foundation

open class DomainNamespace: @unchecked Sendable {
    public let model: String
    public let defaultFields: [String]
    public let defaultDetailFields: [String]?
    public let tagModel: String?
    public let capabilities: [String]
    public let availability: NamespaceAvailability
    internal let client: any OdooClientAPI

    public init(
        client: any OdooClientAPI,
        model: String,
        defaultFields: [String],
        defaultDetailFields: [String]?,
        tagModel: String?,
        capabilities: [String],
        availability: NamespaceAvailability
    ) {
        self.client = client
        self.model = model
        self.defaultFields = defaultFields
        self.defaultDetailFields = defaultDetailFields
        self.tagModel = tagModel
        self.capabilities = capabilities
        self.availability = availability
    }

    open func list(
        domain: Domain = [],
        limit: Int? = 50,
        fields: [String]? = nil,
        order: String = "create_date desc"
    ) async throws -> [OdooRecord] {
        try await client.searchRead(
            model: model,
            domain: domain,
            fields: fields ?? defaultFields,
            limit: limit,
            offset: 0,
            order: order
        )
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
        return record
    }

    public func set(_ recordID: Int, values: OdooRecord) async throws -> Bool {
        try await client.write(model: model, ids: [recordID], values: values)
    }

    public func fields() async throws -> OdooRecord {
        try await client.fieldsGet(model: model)
    }

    public func url(_ recordID: Int) -> URL {
        var base = client.baseURL.absoluteString
        while base.hasSuffix("/") { base.removeLast() }
        return URL(string: "\(base)/web#id=\(recordID)&model=\(model)&view_type=form")!
    }
}
