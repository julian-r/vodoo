import Foundation

/// Build the canonical Odoo web-client URL for a selected transport dialect.
public func buildRecordURL(
    baseURL: URL,
    model: String,
    recordID: Int,
    dialect: TransportDialect
) -> URL {
    var base = baseURL.absoluteString
    while base.hasSuffix("/") { base.removeLast() }
    let modelPath = model.contains(".") ? model : "m-\(model)"
    let value = switch dialect {
    case .json2: "\(base)/odoo/\(modelPath)/\(recordID)"
    case .jsonrpc: "\(base)/web#id=\(recordID)&model=\(model)&view_type=form"
    }
    return URL(string: value)!
}
