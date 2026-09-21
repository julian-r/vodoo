import Foundation

public enum VodooError: Error, Sendable, Equatable, CustomStringConvertible {
    case configuration(String)
    case authentication(String)
    case recordNotFound(model: String, id: Int)
    case operation(String)
    case access(message: String, code: Int, data: OdooRecord)
    case validation(message: String, code: Int, data: OdooRecord)
    case transport(message: String, code: Int, data: OdooRecord)
    case invalidResponse(String)

    public var description: String {
        switch self {
        case let .configuration(message), let .authentication(message),
             let .invalidResponse(message), let .operation(message):
            return message
        case let .recordNotFound(model, id):
            return "Record \(id) not found in \(model)"
        case let .access(message, code, _),
             let .validation(message, code, _),
             let .transport(message, code, _):
            return "[\(code)] \(message)"
        }
    }
}
