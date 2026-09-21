import Foundation

public struct CreateArticleOptions: Sendable, Equatable {
    public var body: RichText?
    public var parentID: Int?
    public var category: String?
    public var icon: String?
    public var extraFields: OdooRecord

    public init(
        body: RichText? = nil,
        parentID: Int? = nil,
        category: String? = nil,
        icon: String? = nil,
        extraFields: OdooRecord = [:]
    ) {
        self.body = body
        self.parentID = parentID
        self.category = category
        self.icon = icon
        self.extraFields = extraFields
    }
}

public extension GeneratedKnowledgeNamespace {
    func create(_ name: String, options: CreateArticleOptions = CreateArticleOptions()) async throws -> Int {
        var values = options.extraFields
        values["name"] = .string(name)
        if let body = options.body { values["body"] = .string(OdooContent.richTextToHTML(body)) }
        if let parentID = options.parentID { values["parent_id"] = .integer(parentID) }
        if let category = options.category { values["category"] = .string(category) }
        if let icon = options.icon { values["icon"] = .string(icon) }
        return try await client.create(model: model, values: values, context: nil)
    }

    func resolveUrl(_ recordID: Int) async throws -> URL { try await resolveURL(recordID) }

    func resolveURL(_ recordID: Int) async throws -> URL {
        let article = try await get(recordID, fields: ["article_url"])
        if let value = article["article_url"]?.stringValue, !value.isEmpty {
            if let absolute = URL(string: value), absolute.scheme != nil { return absolute }
            return URL(string: value, relativeTo: client.baseURL)!
        }
        return url(recordID)
    }
}
