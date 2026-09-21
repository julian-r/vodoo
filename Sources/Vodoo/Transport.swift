import Foundation
#if canImport(FoundationNetworking)
import FoundationNetworking
#endif

public enum TransportDialect: String, Sendable { case jsonrpc, json2 }

public protocol OdooTransportProtocol: Sendable {
    var dialect: TransportDialect { get }
    func getUID() async throws -> Int
    func execute(
        model: String,
        method: String,
        args: [JSONValue],
        kwargs: OdooRecord?
    ) async throws -> JSONValue
}

private func normalizedURL(_ base: URL, path: String) -> URL {
    var text = base.absoluteString
    while text.hasSuffix("/") { text.removeLast() }
    return URL(string: text + path)!
}

private func requestData(
    config: OdooConfig,
    path: String,
    headers: [String: String],
    body: JSONValue
) async throws -> (Data, HTTPURLResponse) {
    var request = URLRequest(url: normalizedURL(config.url, path: path))
    request.httpMethod = "POST"
    request.timeoutInterval = config.timeout
    for (name, value) in config.headers { request.setValue(value, forHTTPHeaderField: name) }
    for (name, value) in headers { request.setValue(value, forHTTPHeaderField: name) }
    request.httpBody = try JSONEncoder().encode(body)
    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse else {
        throw VodooError.invalidResponse("Odoo returned a non-HTTP response")
    }
    return (data, http)
}

private func decodeJSON(_ data: Data) throws -> JSONValue {
    if data.isEmpty { return .null }
    return try JSONDecoder().decode(JSONValue.self, from: data)
}

public func parseJSON2Response(_ wire: String) throws -> JSONValue {
    let trimmed = wire.trimmingCharacters(in: .whitespacesAndNewlines)
    if trimmed.isEmpty || trimmed == "null" || trimmed == "false" { return .null }
    if trimmed == "true" { return .bool(true) }
    let data = Data(trimmed.utf8)
    if let decoded = try? JSONDecoder().decode(JSONValue.self, from: data) {
        return decoded
    }
    return .string(trimmed)
}

public func makeOdooError(message: String, code: Int, data: OdooRecord) -> VodooError {
    let name = data["name"]?.stringValue ?? ""
    if name.hasSuffix("AccessError") || name.hasSuffix("AccessDenied") {
        return .access(message: message, code: code, data: data)
    }
    if name.hasSuffix("ValidationError") {
        return .validation(message: message, code: code, data: data)
    }
    return .transport(message: message, code: code, data: data)
}

private func transportError(data: Data, status: Int) -> VodooError {
    let payload = (try? decodeJSON(data).objectValue) ?? [:]
    let message = payload["message"]?.stringValue ?? "HTTP \(status)"
    let nested = payload["data"]?.objectValue ?? payload
    return makeOdooError(message: message, code: status, data: nested)
}

public func buildLegacyPayload(
    service: String,
    method: String,
    args: [JSONValue]
) -> JSONValue {
    .object([
        "jsonrpc": .string("2.0"),
        "method": .string("call"),
        "params": .object([
            "service": .string(service), "method": .string(method), "args": .array(args),
        ]),
        "id": .null,
    ])
}

public func buildJSON2Body(
    method: String,
    args: [JSONValue],
    kwargs: OdooRecord? = nil
) throws -> OdooRecord {
    var body: OdooRecord = [:]
    switch method {
    case "search", "search_read":
        if let first = args.first { body["domain"] = first }
    case "read":
        if !args.isEmpty { body["ids"] = args[0] }
        if args.count > 1 { body["fields"] = args[1] }
    case "create":
        if let first = args.first {
            if case .array = first {
                body["vals_list"] = first
            } else {
                body["vals_list"] = .array([first])
            }
        }
    case "write":
        if !args.isEmpty { body["ids"] = args[0] }
        if args.count > 1 { body["vals"] = args[1] }
    case "unlink":
        if let first = args.first { body["ids"] = first }
    case "fields_get":
        if let first = args.first { body["allfields"] = first }
    default:
        if args.count == 1, case let .array(ids) = args[0], ids.allSatisfy({ $0.intValue != nil }) {
            body["ids"] = args[0]
        } else if !args.isEmpty {
            throw VodooError.configuration(
                "JSON-2 method \(method) requires named keyword arguments"
            )
        }
    }
    for (key, value) in kwargs ?? [:] { body[key] = value }
    if let domain = body.removeValue(forKey: "args") { body["domain"] = domain }
    return body
}

public actor LegacyTransport: OdooTransportProtocol {
    public nonisolated let dialect = TransportDialect.jsonrpc
    private let config: OdooConfig
    private let retryPolicy: RetryPolicy
    private var uid: Int?

    public init(config: OdooConfig, retryPolicy: RetryPolicy = RetryPolicy()) {
        self.config = config
        self.retryPolicy = retryPolicy
    }

    public func getUID() async throws -> Int {
        if let uid { return uid }
        let result = try await callService(
            service: "common",
            method: "authenticate",
            args: [.string(config.database), .string(config.username), .string(config.password), .object([:])]
        )
        guard let value = result.intValue, value > 0 else {
            throw VodooError.authentication("Authentication failed")
        }
        uid = value
        return value
    }

    public func execute(
        model: String,
        method: String,
        args: [JSONValue] = [],
        kwargs: OdooRecord? = nil
    ) async throws -> JSONValue {
        let userID = try await getUID()
        let wireArgs: [JSONValue] = [
            .string(config.database), .integer(userID), .string(config.password),
            .string(model), .string(method), .array(args), .object(kwargs ?? [:]),
        ]
        for attempt in 0 ... retryPolicy.maxRetries {
            do {
                return try await callService(
                    service: "object",
                    method: "execute_kw",
                    args: wireArgs
                )
            } catch is URLError where attempt < retryPolicy.maxRetries
                && retryPolicy.isRetryable(method: method) {
                try await Task.sleep(for: .seconds(retryPolicy.delay(attempt: attempt)))
            }
        }
        throw VodooError.invalidResponse("Retry loop exited unexpectedly")
    }

    private func callService(
        service: String,
        method: String,
        args: [JSONValue]
    ) async throws -> JSONValue {
        let payload = buildLegacyPayload(service: service, method: method, args: args)
        let (data, response) = try await requestData(
            config: config,
            path: "/jsonrpc",
            headers: ["Content-Type": "application/json"],
            body: payload
        )
        guard (200 ..< 300).contains(response.statusCode) else {
            throw transportError(data: data, status: response.statusCode)
        }
        let object = try decodeJSON(data).objectValue ?? [:]
        if let error = object["error"]?.objectValue {
            let code = error["code"]?.intValue ?? -1
            let nested = error["data"]?.objectValue ?? [:]
            let message = nested["message"]?.stringValue
                ?? error["message"]?.stringValue
                ?? "Unknown error"
            throw makeOdooError(message: message, code: code, data: nested)
        }
        return object["result"] ?? .null
    }
}

public actor JSON2Transport: OdooTransportProtocol {
    public nonisolated let dialect = TransportDialect.json2
    private let config: OdooConfig
    private let retryPolicy: RetryPolicy
    private var uid: Int?

    public init(config: OdooConfig, retryPolicy: RetryPolicy = RetryPolicy()) {
        self.config = config
        self.retryPolicy = retryPolicy
    }

    public func getUID() async throws -> Int {
        if let uid { return uid }
        let result = try await execute(
            model: "res.users",
            method: "search_read",
            args: [.array([.array([.string("login"), .string("="), .string(config.username)])])],
            kwargs: ["fields": .array([.string("id")]), "limit": .integer(1)]
        )
        guard case let .array(records) = result,
              let first = records.first?.objectValue,
              let value = first["id"]?.intValue,
              value > 0 else {
            throw VodooError.authentication("Authentication failed")
        }
        uid = value
        return value
    }

    public func execute(
        model: String,
        method: String,
        args: [JSONValue] = [],
        kwargs: OdooRecord? = nil
    ) async throws -> JSONValue {
        let body = try buildJSON2Body(method: method, args: args, kwargs: kwargs)
        var headers = [
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "bearer \(config.password)",
            "User-Agent": "Vodoo",
        ]
        if !config.database.isEmpty { headers["X-Odoo-Database"] = config.database }
        for attempt in 0 ... retryPolicy.maxRetries {
            do {
                let (data, response) = try await requestData(
                    config: config,
                    path: "/json/2/\(model)/\(method)",
                    headers: headers,
                    body: .object(body)
                )
                guard (200 ..< 300).contains(response.statusCode) else {
                    throw transportError(data: data, status: response.statusCode)
                }
                return try parseJSON2Response(String(decoding: data, as: UTF8.self))
            } catch is URLError where attempt < retryPolicy.maxRetries
                && retryPolicy.isRetryable(method: method) {
                try await Task.sleep(for: .seconds(retryPolicy.delay(attempt: attempt)))
            }
        }
        throw VodooError.invalidResponse("Retry loop exited unexpectedly")
    }
}
