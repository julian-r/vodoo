import Foundation

public enum RecordReference: Sendable, Equatable, ExpressibleByIntegerLiteral, ExpressibleByStringLiteral {
    case id(Int)
    case name(String)
    public init(integerLiteral value: Int) { self = .id(value) }
    public init(stringLiteral value: String) { self = .name(value) }
}

public struct DocumentFolder: Sendable, Equatable {
    public let id: Int
    public let name: String
    public let parentFolder: JSONValue?
    public var depth: Int?
    public var path: String?

    public init(
        id: Int, name: String, parentFolder: JSONValue? = nil,
        depth: Int? = nil, path: String? = nil
    ) {
        self.id = id
        self.name = name
        self.parentFolder = parentFolder
        self.depth = depth
        self.path = path
    }
}

public struct DocumentUploadOptions: Sendable, Equatable {
    public var folder: RecordReference?
    public var folderID: Int?
    public var tags: [RecordReference]
    public var owner: RecordReference?
    public var mimetype: String?

    public init(
        folder: RecordReference? = nil, folderID: Int? = nil,
        tags: [RecordReference] = [], owner: RecordReference? = nil, mimetype: String? = nil
    ) {
        self.folder = folder
        self.folderID = folderID
        self.tags = tags
        self.owner = owner
        self.mimetype = mimetype
    }
}

public struct DownloadedDocument: Sendable, Equatable {
    public let id: Int
    public let name: String
    public let data: Data
    public let mimetype: String?
}

public extension GeneratedDocumentNamespace {
    func folders(limit: Int? = 50, tree: Bool = false) async throws -> [DocumentFolder] {
        let modern = try await usesDocumentFolderRecords()
        let records = try await client.searchRead(
            model: modern ? "documents.document" : "documents.folder",
            domain: modern
                ? [.array([.string("type"), .string("="), .string("folder")])]
                : [],
            fields: modern ? ["id", "name", "folder_id"] : ["id", "name", "parent_folder_id"],
            limit: limit,
            offset: 0,
            order: "name, id"
        )
        let values = records.compactMap { record -> DocumentFolder? in
            guard let id = record["id"]?.intValue, let name = record["name"]?.stringValue else {
                return nil
            }
            return DocumentFolder(
                id: id, name: name,
                parentFolder: record[modern ? "folder_id" : "parent_folder_id"]
            )
        }
        return tree ? orderDocumentFolderTree(values) : values
    }

    func resolveFolder(_ folder: Int) async throws -> Int {
        try positiveID(folder)
    }

    func resolveFolder(_ folder: String) async throws -> Int {
        if let direct = Int(folder.trimmingCharacters(in: .whitespacesAndNewlines)) {
            return try positiveID(direct)
        }
        return try await resolveFolderName(folder)
    }

    func upload(
        data: Data,
        name: String,
        options: DocumentUploadOptions
    ) async throws -> Int {
        let folderID = try await resolveFolderInput(options)
        var tagIDs: [Int] = []
        for tag in options.tags { tagIDs.append(try await resolveNamedRecord("documents.tag", tag)) }
        let ownerID = try await options.owner.asyncMap { try await resolveNamedRecord("res.users", $0) }
        var values: OdooRecord = [
            "name": .string(name),
            "datas": .string(OdooBinaryCodec.encode(data)),
            "mimetype": .string(options.mimetype ?? guessMimetype(name)),
            "folder_id": .integer(folderID),
        ]
        if !tagIDs.isEmpty { values["tag_ids"] = .array([Command.set(tagIDs).wireValue]) }
        if let ownerID { values["owner_id"] = .integer(ownerID) }
        return try await client.create(model: "documents.document", values: values, context: nil)
    }

    func downloadFile(_ documentID: Int) async throws -> DownloadedDocument {
        let records = try await client.read(
            model: "documents.document", ids: [documentID],
            fields: ["name", "type", "file_size", "datas", "mimetype"]
        )
        guard let document = records.first else {
            throw VodooError.recordNotFound(model: "documents.document", id: documentID)
        }
        let data: Data
        if let encoded = document["datas"]?.stringValue {
            data = try OdooBinaryCodec.decode(encoded)
        } else if document["type"]?.stringValue == "binary", document["file_size"]?.intValue == 0 {
            data = Data()
        } else {
            throw VodooError.recordNotFound(model: "documents.document", id: documentID)
        }
        return DownloadedDocument(
            id: documentID,
            name: safeDocumentFilename(document["name"]?.stringValue, documentID: documentID),
            data: data,
            mimetype: document["mimetype"]?.stringValue
        )
    }

    private func usesDocumentFolderRecords() async throws -> Bool {
        let fields = try await client.fieldsGet(
            model: "documents.document", fields: ["type"], attributes: ["selection"]
        )
        guard let selection = fields["type"]?.objectValue?["selection"] else { return false }
        if let values = selection.arrayValue {
            return values.contains { $0.arrayValue?.first?.stringValue == "folder" }
        }
        return selection.objectValue?["folder"] != nil
    }

    private func resolveFolderInput(_ options: DocumentUploadOptions) async throws -> Int {
        guard (options.folder == nil) != (options.folderID == nil) else {
            throw VodooError.operation("Specify exactly one of folder or folderID")
        }
        if let id = options.folderID { return try positiveID(id) }
        guard let folder = options.folder else { throw VodooError.operation("Specify a folder") }
        switch folder {
        case let .id(id): return try positiveID(id)
        case let .name(name): return try await resolveFolder(name)
        }
    }

    private func resolveFolderName(_ name: String) async throws -> Int {
        let modern = try await usesDocumentFolderRecords()
        let model = modern ? "documents.document" : "documents.folder"
        var domain: Domain = []
        if modern { domain.append(.array([.string("type"), .string("="), .string("folder")])) }
        domain.append(.array([.string("name"), .string("="), .string(name)]))
        let records = try await client.searchRead(
            model: model, domain: domain, fields: ["id", "name"],
            limit: 2, offset: 0, order: nil
        )
        return try requireUniqueID(records, model: model, value: name)
    }

    private func resolveNamedRecord(_ model: String, _ value: RecordReference) async throws -> Int {
        switch value {
        case let .id(id): return try positiveID(id)
        case let .name(name):
            let domain: Domain = model == "res.users"
                ? [
                    .string("|"),
                    .array([.string("login"), .string("="), .string(name)]),
                    .array([.string("name"), .string("="), .string(name)]),
                ]
                : [.array([.string("name"), .string("="), .string(name)])]
            let records = try await client.searchRead(
                model: model, domain: domain,
                fields: model == "res.users" ? ["id", "name", "login"] : ["id", "name"],
                limit: 2, offset: 0, order: nil
            )
            return try requireUniqueID(records, model: model, value: name)
        }
    }
}

public func orderDocumentFolderTree(_ folders: [DocumentFolder]) -> [DocumentFolder] {
    let ids = Set(folders.map(\.id))
    var children: [Int?: [DocumentFolder]] = [:]
    for folder in folders {
        let relation = relationID(folder.parentFolder)
        let parent = relation.flatMap { ids.contains($0) ? $0 : nil }
        children[parent, default: []].append(folder)
    }
    for key in children.keys {
        children[key]?.sort { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending
            || ($0.name.caseInsensitiveCompare($1.name) == .orderedSame && $0.id < $1.id) }
    }
    var result: [DocumentFolder] = []
    var visited = Set<Int>()
    func visit(_ folder: DocumentFolder, depth: Int, parents: [String]) {
        guard visited.insert(folder.id).inserted else { return }
        result.append(DocumentFolder(
            id: folder.id, name: folder.name, parentFolder: folder.parentFolder,
            depth: depth, path: (parents + [folder.name]).joined(separator: " / ")
        ))
        for child in children[folder.id] ?? [] {
            visit(child, depth: depth + 1, parents: parents + [folder.name])
        }
    }
    for root in children[nil] ?? [] { visit(root, depth: 0, parents: []) }
    for folder in folders.sorted(by: { $0.name.localizedCaseInsensitiveCompare($1.name) == .orderedAscending }) {
        visit(folder, depth: 0, parents: [])
    }
    return result
}

public func safeDocumentFilename(_ name: String?, documentID: Int) -> String {
    var filename = (name ?? "").replacingOccurrences(of: "\\", with: "/")
        .split(separator: "/", omittingEmptySubsequences: false).last.map(String.init) ?? ""
    let invalid = CharacterSet(charactersIn: "<>:\"/\\|?*").union(.controlCharacters)
    filename = filename.unicodeScalars.map { invalid.contains($0) ? "_" : String($0) }.joined()
    filename = filename.replacingOccurrences(of: #"[. ]+$"#, with: "", options: .regularExpression)
    let stem = filename.split(separator: ".", maxSplits: 1, omittingEmptySubsequences: false).first
        .map(String.init)?.uppercased() ?? ""
    let reserved = Set(["CON", "PRN", "AUX", "NUL"]
        + (1 ... 9).map { "COM\($0)" } + (1 ... 9).map { "LPT\($0)" })
    if reserved.contains(stem) { filename = "_" + filename }
    return filename.isEmpty || filename == "." || filename == ".." ? "document_\(documentID)" : filename
}

private func positiveID(_ id: Int) throws -> Int {
    guard id > 0 else { throw VodooError.operation("Record IDs must be positive integers") }
    return id
}

private func requireUniqueID(_ records: [OdooRecord], model: String, value: String) throws -> Int {
    guard !records.isEmpty else {
        throw VodooError.operation("No \(model) record found matching '\(value)'")
    }
    guard records.count == 1 else {
        throw VodooError.operation("Multiple \(model) records match '\(value)'; use a numeric ID")
    }
    guard let id = records[0]["id"]?.intValue else {
        throw VodooError.operation("\(model) record matching '\(value)' has no numeric ID")
    }
    return id
}

private func guessMimetype(_ name: String) -> String {
    let known = [
        "csv": "text/csv", "gif": "image/gif", "html": "text/html", "jpeg": "image/jpeg",
        "jpg": "image/jpeg", "json": "application/json", "md": "text/markdown",
        "pdf": "application/pdf", "png": "image/png", "svg": "image/svg+xml",
        "txt": "text/plain", "webp": "image/webp", "xml": "application/xml", "zip": "application/zip",
    ]
    return known[name.split(separator: ".").last.map { String($0).lowercased() } ?? ""]
        ?? "application/octet-stream"
}

private extension Optional {
    func asyncMap<T>(_ transform: (Wrapped) async throws -> T) async rethrows -> T? {
        guard let value = self else { return nil }
        return try await transform(value)
    }
}
