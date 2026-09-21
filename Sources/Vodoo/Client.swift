import Foundation

public protocol OdooClientAPI: Sendable {
    var baseURL: URL { get }
    var defaultUserID: Int? { get }
    func getUID() async throws -> Int
    func execute(model: String, method: String, args: [JSONValue], kwargs: OdooRecord?) async throws -> JSONValue
    func search(
        model: String,
        domain: Domain,
        limit: Int?,
        offset: Int,
        order: String?
    ) async throws -> [Int]
    func searchRead(
        model: String,
        domain: Domain,
        fields: [String]?,
        limit: Int?,
        offset: Int,
        order: String?
    ) async throws -> [OdooRecord]
    func read(model: String, ids: [Int], fields: [String]?) async throws -> [OdooRecord]
    func create(model: String, values: OdooRecord, context: OdooRecord?) async throws -> Int
    func write(model: String, ids: [Int], values: OdooRecord) async throws -> Bool
    func unlink(model: String, ids: [Int]) async throws -> Bool
    func fieldsGet(model: String) async throws -> OdooRecord
    func nameSearch(
        model: String,
        name: String,
        domain: Domain,
        limit: Int
    ) async throws -> [NameSearchResult]
}

private actor TransportHolder {
    private let config: OdooConfig
    private let autoDetect: Bool
    private var transport: (any OdooTransportProtocol)?

    init(config: OdooConfig, autoDetect: Bool, transport: (any OdooTransportProtocol)?) {
        self.config = config
        self.autoDetect = autoDetect
        self.transport = transport
    }

    func value() async throws -> any OdooTransportProtocol {
        if let transport { return transport }
        if !autoDetect {
            let legacy = LegacyTransport(config: config)
            transport = legacy
            return legacy
        }
        let json2 = JSON2Transport(config: config)
        do {
            _ = try await json2.getUID()
            transport = json2
            return json2
        } catch is VodooError {
            let legacy = LegacyTransport(config: config)
            transport = legacy
            return legacy
        }
    }
}

public final class OdooClient: OdooClientAPI, @unchecked Sendable {
    public let baseURL: URL
    public let defaultUserID: Int?
    public lazy var projects = GeneratedProjectNamespace(client: self)
    public lazy var tasks = GeneratedTaskNamespace(client: self)
    public lazy var crm = GeneratedCRMNamespace(client: self)
    public lazy var helpdesk = GeneratedHelpdeskNamespace(client: self)
    public lazy var knowledge = GeneratedKnowledgeNamespace(client: self)
    public lazy var documents = GeneratedDocumentNamespace(client: self)
    public lazy var activities = GeneratedActivityNamespace(client: self)
    public lazy var accountMoves = GeneratedAccountMoveNamespace(client: self)

    private let holder: TransportHolder

    public init(
        config: OdooConfig,
        autoDetect: Bool = true,
        transport: (any OdooTransportProtocol)? = nil
    ) {
        baseURL = config.url
        defaultUserID = config.defaultUserID
        holder = TransportHolder(config: config, autoDetect: autoDetect, transport: transport)
    }

    public func getUID() async throws -> Int { try await holder.value().getUID() }

    public func transportDialect() async throws -> TransportDialect {
        try await holder.value().dialect
    }

    public func execute(
        model: String,
        method: String,
        args: [JSONValue] = [],
        kwargs: OdooRecord? = nil
    ) async throws -> JSONValue {
        try await holder.value().execute(model: model, method: method, args: args, kwargs: kwargs)
    }

    public func search(
        model: String,
        domain: Domain = [],
        limit: Int? = nil,
        offset: Int = 0,
        order: String? = nil
    ) async throws -> [Int] {
        var kwargs: OdooRecord = [:]
        if let limit { kwargs["limit"] = .integer(limit) }
        if offset > 0 { kwargs["offset"] = .integer(offset) }
        if let order { kwargs["order"] = .string(order) }
        let result = try await execute(
            model: model,
            method: "search",
            args: [.array(domain)],
            kwargs: kwargs
        )
        guard case let .array(values) = result else {
            throw VodooError.invalidResponse("search returned a non-array result")
        }
        let ids = values.compactMap(\.intValue)
        guard ids.count == values.count else {
            throw VodooError.invalidResponse("search returned an invalid record ID")
        }
        return ids
    }

    public func searchRead(
        model: String,
        domain: Domain = [],
        fields: [String]? = nil,
        limit: Int? = nil,
        offset: Int = 0,
        order: String? = nil
    ) async throws -> [OdooRecord] {
        var kwargs: OdooRecord = [:]
        if let fields { kwargs["fields"] = .array(fields.map(JSONValue.string)) }
        if let limit { kwargs["limit"] = .integer(limit) }
        if offset > 0 { kwargs["offset"] = .integer(offset) }
        if let order { kwargs["order"] = .string(order) }
        let result = try await execute(
            model: model,
            method: "search_read",
            args: [.array(domain)],
            kwargs: kwargs
        )
        guard case let .array(values) = result else {
            throw VodooError.invalidResponse("search_read returned a non-array result")
        }
        return values.compactMap(\.objectValue).map(normalizeFalse)
    }

    public func read(model: String, ids: [Int], fields: [String]? = nil) async throws -> [OdooRecord] {
        var args: [JSONValue] = [.array(ids.map(JSONValue.integer))]
        if let fields { args.append(.array(fields.map(JSONValue.string))) }
        let result = try await execute(model: model, method: "read", args: args)
        guard case let .array(values) = result else {
            throw VodooError.invalidResponse("read returned a non-array result")
        }
        return values.compactMap(\.objectValue).map(normalizeFalse)
    }

    public func create(model: String, values: OdooRecord, context: OdooRecord? = nil) async throws -> Int {
        let kwargs = context.map { ["context": JSONValue.object($0)] }
        let result = try await execute(model: model, method: "create", args: [.object(values)], kwargs: kwargs)
        let value: JSONValue
        if case let .array(items) = result, items.count == 1 { value = items[0] } else { value = result }
        guard let id = value.intValue, id > 0 else {
            throw VodooError.invalidResponse("Create returned an invalid record ID")
        }
        return id
    }

    public func write(model: String, ids: [Int], values: OdooRecord) async throws -> Bool {
        let result = try await execute(
            model: model,
            method: "write",
            args: [.array(ids.map(JSONValue.integer)), .object(values)]
        )
        guard case let .bool(value) = result else {
            throw VodooError.invalidResponse("write returned a non-boolean result")
        }
        return value
    }

    public func unlink(model: String, ids: [Int]) async throws -> Bool {
        let result = try await execute(
            model: model,
            method: "unlink",
            args: [.array(ids.map(JSONValue.integer))]
        )
        guard case let .bool(value) = result else {
            throw VodooError.invalidResponse("unlink returned a non-boolean result")
        }
        return value
    }

    public func fieldsGet(model: String) async throws -> OdooRecord {
        let result = try await execute(model: model, method: "fields_get", args: [.array([])])
        guard let fields = result.objectValue else {
            throw VodooError.invalidResponse("fields_get returned a non-object result")
        }
        return fields
    }

    public func nameSearch(
        model: String,
        name: String,
        domain: Domain = [],
        limit: Int = 100
    ) async throws -> [NameSearchResult] {
        let result = try await execute(
            model: model,
            method: "name_search",
            args: [],
            kwargs: [
                "name": .string(name),
                "args": .array(domain),
                "limit": .integer(limit),
            ]
        )
        guard case let .array(rows) = result else {
            throw VodooError.invalidResponse("name_search returned a non-array result")
        }
        return rows.compactMap { row in
            guard case let .array(pair) = row, pair.count >= 2,
                  let id = pair[0].intValue, let name = pair[1].stringValue else { return nil }
            return NameSearchResult(id: id, name: name)
        }
    }
}

private func normalizeFalse(_ record: OdooRecord) -> OdooRecord {
    record.mapValues { value in value == .bool(false) ? .null : value }
}
