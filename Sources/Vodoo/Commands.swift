public enum Command: Sendable, Equatable {
    case create(OdooRecord)
    case update(Int, OdooRecord)
    case delete(Int)
    case unlink(Int)
    case link(Int)
    case clear
    case set([Int])

    public var wireValue: JSONValue {
        switch self {
        case let .create(values): .array([.integer(0), .integer(0), .object(values)])
        case let .update(id, values): .array([.integer(1), .integer(id), .object(values)])
        case let .delete(id): .array([.integer(2), .integer(id), .integer(0)])
        case let .unlink(id): .array([.integer(3), .integer(id), .integer(0)])
        case let .link(id): .array([.integer(4), .integer(id), .integer(0)])
        case .clear: .array([.integer(5), .integer(0), .integer(0)])
        case let .set(ids): .array([.integer(6), .integer(0), .array(ids.map(JSONValue.integer))])
        }
    }
}
