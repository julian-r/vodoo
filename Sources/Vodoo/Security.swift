import Foundation

public struct SecurityAccessDefinition: Sendable, Equatable {
    public let model: String
    public let read: Bool
    public let write: Bool
    public let create: Bool
    public let unlink: Bool

    public init(model: String, read: Bool, write: Bool, create: Bool, unlink: Bool) {
        self.model = model
        self.read = read
        self.write = write
        self.create = create
        self.unlink = unlink
    }
}

public struct SecurityRuleDefinition: Sendable, Equatable {
    public let model: String
    public let domain: String
    public let read: Bool
    public let write: Bool
    public let create: Bool
    public let unlink: Bool

    public init(
        model: String, domain: String, read: Bool, write: Bool, create: Bool, unlink: Bool
    ) {
        self.model = model
        self.domain = domain
        self.read = read
        self.write = write
        self.create = create
        self.unlink = unlink
    }
}

public struct SecurityGroupDefinition: Sendable, Equatable {
    public let name: String
    public let comment: String
    public let access: [SecurityAccessDefinition]
    public let rules: [SecurityRuleDefinition]

    public init(
        name: String, comment: String, access: [SecurityAccessDefinition],
        rules: [SecurityRuleDefinition] = []
    ) {
        self.name = name
        self.comment = comment
        self.access = access
        self.rules = rules
    }
}

public struct SecurityGroupResult: Sendable, Equatable {
    public let groupIDs: [String: Int]
    public let warnings: [String]
}

public struct CreatedUser: Sendable, Equatable {
    public let userID: Int
    public let password: String
}

public final class SecurityNamespace: @unchecked Sendable {
    private let client: any OdooClientAPI
    public init(client: any OdooClientAPI) { self.client = client }

    public func createGroups() async throws -> SecurityGroupResult {
        var warnings: [String] = []
        var groupIDs: [String: Int] = [:]
        for group in SECURITY_GROUP_DEFINITIONS {
            let groupID = try await ensureGroup(group)
            groupIDs[group.name] = groupID
            for definition in group.access {
                guard let modelID = try await getModelID(definition.model) else {
                    warnings.append("Model '\(definition.model)' not found; skipping access")
                    continue
                }
                _ = try await ensureAccess(
                    groupID: groupID, groupName: group.name,
                    modelID: modelID, definition: definition
                )
            }
            for definition in group.rules {
                guard let modelID = try await getModelID(definition.model) else {
                    warnings.append("Model '\(definition.model)' not found; skipping rule")
                    continue
                }
                _ = try await ensureRule(
                    groupID: groupID, groupName: group.name,
                    modelID: modelID, definition: definition
                )
            }
        }
        return SecurityGroupResult(groupIDs: groupIDs, warnings: warnings)
    }

    public func getGroupIDs(_ groupNames: [String]) async throws -> SecurityGroupResult {
        var warnings: [String] = []
        var groupIDs: [String: Int] = [:]
        for name in groupNames {
            let ids = try await client.search(
                model: "res.groups",
                domain: [.array([.string("name"), .string("="), .string(name)])],
                limit: 1, offset: 0, order: nil
            )
            if let id = ids.first { groupIDs[name] = id }
            else { warnings.append("Group '\(name)' not found") }
        }
        return SecurityGroupResult(groupIDs: groupIDs, warnings: warnings)
    }

    public func assign(
        userID: Int,
        groupIDs: [Int],
        removeDefaultGroups: Bool = true
    ) async throws {
        var commands: [JSONValue] = []
        if removeDefaultGroups {
            for xmlID in ["base.group_user", "base.group_portal"] {
                if let id = try await getGroupIDByXMLID(xmlID) {
                    commands.append(Command.unlink(id).wireValue)
                }
            }
        }
        commands.append(contentsOf: groupIDs.map { Command.link($0).wireValue })
        let field = try await groupsField()
        _ = try await client.write(
            model: "res.users", ids: [userID], values: [field: .array(commands)]
        )
    }

    public func resolveUser(userID: Int? = nil, login: String? = nil) async throws -> Int {
        if let userID { return userID }
        guard let login, !login.isEmpty else { throw VodooError.operation("Provide userID or login") }
        let ids = try await client.search(
            model: "res.users",
            domain: [.array([.string("login"), .string("="), .string(login)])],
            limit: 1, offset: 0, order: nil
        )
        guard let id = ids.first else {
            throw VodooError.operation("User with login '\(login)' not found")
        }
        return id
    }

    public func createUser(
        name: String,
        login: String,
        password: String? = nil,
        email: String? = nil
    ) async throws -> CreatedUser {
        let password = password ?? generatePassword()
        let field = try await groupsField()
        let id = try await client.create(model: "res.users", values: [
            "name": .string(name),
            "login": .string(login),
            "email": .string(email ?? login),
            "password": .string(password),
            field: .array([Command.set([]).wireValue]),
        ], context: nil)
        return CreatedUser(userID: id, password: password)
    }

    public func setPassword(_ userID: Int, password: String? = nil) async throws -> String {
        let password = password ?? generatePassword()
        _ = try await client.write(
            model: "res.users", ids: [userID], values: ["password": .string(password)]
        )
        return password
    }

    public func getUser(_ userID: Int) async throws -> OdooRecord {
        let field = try await groupsField()
        let records = try await client.searchRead(
            model: "res.users",
            domain: [.array([.string("id"), .string("="), .integer(userID)])],
            fields: ["name", "login", "email", "active", "share", field, "partner_id"],
            limit: 1, offset: 0, order: nil
        )
        guard let user = records.first else { throw VodooError.operation("User \(userID) not found") }
        return user
    }

    private func groupsField() async throws -> String {
        let fields = try await client.fieldsGet(
            model: "res.users", fields: ["group_ids"], attributes: ["type"]
        )
        return fields["group_ids"]?.objectValue?["type"]?.stringValue == "many2many"
            ? "group_ids" : "groups_id"
    }

    private func ensureGroup(_ group: SecurityGroupDefinition) async throws -> Int {
        let ids = try await client.search(
            model: "res.groups",
            domain: [.array([.string("name"), .string("="), .string(group.name)])],
            limit: 1, offset: 0, order: nil
        )
        if let id = ids.first { return id }
        return try await client.create(model: "res.groups", values: [
            "name": .string(group.name), "comment": .string(group.comment),
        ], context: nil)
    }

    private func ensureAccess(
        groupID: Int,
        groupName: String,
        modelID: Int,
        definition: SecurityAccessDefinition
    ) async throws -> Int {
        let name = accessName(groupName, definition.model)
        let ids = try await client.search(
            model: "ir.model.access",
            domain: [
                .array([.string("name"), .string("="), .string(name)]),
                .array([.string("model_id"), .string("="), .integer(modelID)]),
                .array([.string("group_id"), .string("="), .integer(groupID)]),
            ],
            limit: 1, offset: 0, order: nil
        )
        if let id = ids.first { return id }
        return try await client.create(model: "ir.model.access", values: [
            "name": .string(name), "model_id": .integer(modelID), "group_id": .integer(groupID),
            "perm_read": .bool(definition.read), "perm_write": .bool(definition.write),
            "perm_create": .bool(definition.create), "perm_unlink": .bool(definition.unlink),
        ], context: nil)
    }

    private func ensureRule(
        groupID: Int,
        groupName: String,
        modelID: Int,
        definition: SecurityRuleDefinition
    ) async throws -> Int {
        let name = ruleName(groupName, definition.model)
        let ids = try await client.search(
            model: "ir.rule",
            domain: [
                .array([.string("name"), .string("="), .string(name)]),
                .array([.string("model_id"), .string("="), .integer(modelID)]),
            ],
            limit: 1, offset: 0, order: nil
        )
        if let id = ids.first { return id }
        return try await client.create(model: "ir.rule", values: [
            "name": .string(name), "model_id": .integer(modelID),
            "groups": .array([Command.link(groupID).wireValue]),
            "domain_force": .string(definition.domain),
            "perm_read": .bool(definition.read), "perm_write": .bool(definition.write),
            "perm_create": .bool(definition.create), "perm_unlink": .bool(definition.unlink),
        ], context: nil)
    }

    private func getModelID(_ model: String) async throws -> Int? {
        try await client.search(
            model: "ir.model",
            domain: [.array([.string("model"), .string("="), .string(model)])],
            limit: 1, offset: 0, order: nil
        ).first
    }

    private func getGroupIDByXMLID(_ xmlID: String) async throws -> Int? {
        let parts = xmlID.split(separator: ".", maxSplits: 1).map(String.init)
        guard parts.count == 2 else { return nil }
        let records = try await client.searchRead(
            model: "ir.model.data",
            domain: [
                .array([.string("module"), .string("="), .string(parts[0])]),
                .array([.string("name"), .string("="), .string(parts[1])]),
            ],
            fields: ["res_id"], limit: 1, offset: 0, order: nil
        )
        return records.first?["res_id"]?.intValue
    }
}

private let passwordAlphabet = Array(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*"
)

private func generatePassword() -> String {
    var generator = SystemRandomNumberGenerator()
    return String((0 ..< 24).map { _ in passwordAlphabet.randomElement(using: &generator)! })
}

private func securitySlug(_ value: String) -> String {
    value.lowercased().replacingOccurrences(of: " ", with: "_")
}

private func accessName(_ group: String, _ model: String) -> String {
    "vodoo_\(securitySlug(group))_access_\(model.replacingOccurrences(of: ".", with: "_"))"
}

private func ruleName(_ group: String, _ model: String) -> String {
    "vodoo_\(securitySlug(group))_rule_\(model.replacingOccurrences(of: ".", with: "_"))"
}
