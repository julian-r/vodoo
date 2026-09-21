import Foundation

/// CRUD escape hatch for installation-specific Odoo models and custom modules.
public struct GenericNamespace: Sendable {
    private let client: any OdooClientAPI

    public init(client: any OdooClientAPI) { self.client = client }

    public func create(
        model: String,
        values: OdooRecord,
        context: OdooRecord? = nil
    ) async throws -> Int {
        try await client.create(model: model, values: values, context: context)
    }

    public func update(model: String, recordID: Int, values: OdooRecord) async throws -> Bool {
        try await client.write(model: model, ids: [recordID], values: values)
    }

    public func delete(model: String, recordID: Int) async throws -> Bool {
        try await client.unlink(model: model, ids: [recordID])
    }

    /// Search and return records, matching the Python and TypeScript generic namespaces.
    public func search(
        model: String,
        domain: Domain = [],
        fields: [String]? = nil,
        limit: Int? = 50,
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

    public func call(
        model: String,
        method: String,
        args: [JSONValue] = [],
        kwargs: OdooRecord? = nil
    ) async throws -> JSONValue {
        try await client.execute(model: model, method: method, args: args, kwargs: kwargs)
    }
}

/// Model-bound low-level ORM API for callers that prefer a reusable model handle.
public struct ModelNamespace: Sendable {
    public let model: String
    private let client: any OdooClientAPI

    public init(model: String, client: any OdooClientAPI) {
        self.model = model
        self.client = client
    }

    public func search(
        domain: Domain = [], limit: Int? = nil, offset: Int = 0, order: String? = nil
    ) async throws -> [Int] {
        try await client.search(model: model, domain: domain, limit: limit, offset: offset, order: order)
    }

    public func read(_ ids: [Int], fields: [String]? = nil) async throws -> [OdooRecord] {
        try await client.read(model: model, ids: ids, fields: fields)
    }

    public func searchRead(
        domain: Domain = [], fields: [String]? = nil, limit: Int? = nil,
        offset: Int = 0, order: String? = nil
    ) async throws -> [OdooRecord] {
        try await client.searchRead(
            model: model, domain: domain, fields: fields, limit: limit, offset: offset, order: order
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

    public func fields(_ names: [String]? = nil, attributes: [String]? = nil) async throws -> OdooRecord {
        try await client.fieldsGet(model: model, fields: names, attributes: attributes)
    }

    public func nameSearch(
        _ name: String, domain: Domain = [], limit: Int = 7
    ) async throws -> [NameSearchResult] {
        try await client.nameSearch(model: model, name: name, domain: domain, limit: limit)
    }
}

public extension OdooClient {
    func model(_ name: String) -> ModelNamespace { ModelNamespace(model: name, client: self) }
}
