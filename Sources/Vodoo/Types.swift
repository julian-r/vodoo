import Foundation

public enum JSONValue: Codable, Sendable, Equatable {
    case null
    case bool(Bool)
    case number(Double)
    case string(String)
    case date(Date)
    case dateTime(Date)
    case array([JSONValue])
    case object([String: JSONValue])

    public init(from decoder: any Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() { self = .null }
        else if let value = try? container.decode(Bool.self) { self = .bool(value) }
        else if let value = try? container.decode(Double.self) { self = .number(value) }
        else if let value = try? container.decode(String.self) { self = .string(value) }
        else if let value = try? container.decode([JSONValue].self) { self = .array(value) }
        else { self = .object(try container.decode([String: JSONValue].self)) }
    }

    public func encode(to encoder: any Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .null: try container.encodeNil()
        case let .bool(value): try container.encode(value)
        case let .number(value): try container.encode(value)
        case let .string(value): try container.encode(value)
        case let .date(value): try container.encode(OdooDateCodec.formatDate(value))
        case let .dateTime(value): try container.encode(OdooDateCodec.formatDateTime(value))
        case let .array(value): try container.encode(value)
        case let .object(value): try container.encode(value)
        }
    }

    public static func integer(_ value: Int) -> JSONValue { .number(Double(value)) }

    public var intValue: Int? {
        guard case let .number(value) = self, value.rounded() == value,
              value >= Double(Int.min), value <= Double(Int.max) else { return nil }
        return Int(value)
    }

    public var stringValue: String? {
        guard case let .string(value) = self else { return nil }
        return value
    }

    public var dateValue: Date? {
        switch self {
        case let .date(value), let .dateTime(value): return value
        default: return nil
        }
    }

    public var objectValue: [String: JSONValue]? {
        guard case let .object(value) = self else { return nil }
        return value
    }

    public var arrayValue: [JSONValue]? {
        guard case let .array(value) = self else { return nil }
        return value
    }

    public var boolValue: Bool? {
        guard case let .bool(value) = self else { return nil }
        return value
    }

    public var doubleValue: Double? {
        guard case let .number(value) = self else { return nil }
        return value
    }

    public var isNull: Bool { self == .null }
}

public typealias OdooRecord = [String: JSONValue]
public typealias Domain = [JSONValue]

public struct NameSearchResult: Sendable, Equatable {
    public let id: Int
    public let name: String

    public init(id: Int, name: String) {
        self.id = id
        self.name = name
    }
}

public struct OdooConfig: Sendable {
    public let url: URL
    public let database: String
    public let username: String
    public let password: String
    public let defaultUserID: Int?
    public let timeout: TimeInterval
    public let headers: [String: String]

    public init(
        url: URL,
        database: String,
        username: String,
        password: String,
        defaultUserID: Int? = nil,
        timeout: TimeInterval = 30,
        headers: [String: String] = [:]
    ) {
        self.url = url
        self.database = database.trimmingCharacters(in: .whitespacesAndNewlines)
        self.username = username.trimmingCharacters(in: .whitespacesAndNewlines)
        self.password = password
        self.defaultUserID = defaultUserID
        self.timeout = timeout
        self.headers = headers
    }
}

public struct NamespaceAvailability: Sendable, Equatable {
    public let module: String
    public let editions: [String]
    public let minVersion: Int
    public let maxVersion: Int?

    public init(module: String, editions: [String], minVersion: Int, maxVersion: Int? = nil) {
        self.module = module
        self.editions = editions
        self.minVersion = minVersion
        self.maxVersion = maxVersion
    }
}
