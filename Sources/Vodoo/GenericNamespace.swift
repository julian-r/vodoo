import Foundation

/// CRUD escape hatch for installation-specific Odoo models and custom modules.
public struct GenericNamespace: Sendable {
    public let model: String
    private let client: any OdooClientAPI

    public init(model: String, client: any OdooClientAPI) {
        self.model = model
        self.client = client
    }

    public func search(
        domain: Domain = [],
        limit: Int? = nil,
        offset: Int = 0,
        order: String? = nil
    ) async throws -> [Int] {
        try await client.search(
            model: model,
            domain: domain,
            limit: limit,
            offset: offset,
            order: order
        )
    }

    public func read(_ ids: [Int], fields: [String]? = nil) async throws -> [OdooRecord] {
        try await client.read(model: model, ids: ids, fields: fields)
    }

    public func searchRead(
        domain: Domain = [],
        fields: [String]? = nil,
        limit: Int? = nil,
        offset: Int = 0,
        order: String? = nil
    ) async throws -> [OdooRecord] {
        try await client.searchRead(
            model: model,
            domain: domain,
            fields: fields,
            limit: limit,
            offset: offset,
            order: order
        )
    }

    public func create(_ values: OdooRecord, context: OdooRecord? = nil) async throws -> Int {
        try await client.create(model: model, values: values, context: context)
    }

    public func write(_ ids: [Int], values: OdooRecord) async throws -> Bool {
        try await client.write(model: model, ids: ids, values: values)
    }

    public func unlink(_ ids: [Int]) async throws -> Bool {
        try await client.unlink(model: model, ids: ids)
    }

    public func fields() async throws -> OdooRecord {
        try await client.fieldsGet(model: model)
    }

    public func nameSearch(
        _ name: String,
        domain: Domain = [],
        limit: Int = 100
    ) async throws -> [NameSearchResult] {
        try await client.nameSearch(model: model, name: name, domain: domain, limit: limit)
    }
}

public extension OdooClient {
    func generic(_ model: String) -> GenericNamespace {
        GenericNamespace(model: model, client: self)
    }
}
