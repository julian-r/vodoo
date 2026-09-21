import Foundation

public extension GeneratedProjectNamespace {
    func resolveProjectId(_ project: String) async throws -> Int { try await resolveProjectID(project) }
    func resolveProjectId(_ project: Int) async throws -> Int { project }

    func resolveProjectID(_ project: String) async throws -> Int {
        if let id = Int(project), id >= 0 { return id }
        let candidates = try await client.searchRead(
            model: "project.project",
            domain: [.array([.string("name"), .string("=ilike"), .string(project)])],
            fields: ["id", "name"],
            limit: nil,
            offset: 0,
            order: "id"
        )
        let expected = project.lowercased().replacingOccurrences(of: "ß", with: "ss")
        let matches = candidates.filter {
            $0["name"]?.stringValue?.lowercased().replacingOccurrences(of: "ß", with: "ss") == expected
        }
        guard !matches.isEmpty else { throw VodooError.operation("Project '\(project)' not found") }
        guard matches.count == 1 else {
            throw VodooError.operation("Project name '\(project)' is ambiguous; use a project ID")
        }
        guard let id = matches[0]["id"]?.intValue else {
            throw VodooError.invalidResponse("Project has no numeric ID")
        }
        return id
    }

    func resolveProjectID(_ project: Int) async throws -> Int { project }

    func milestones(_ project: String) async throws -> [OdooRecord] {
        try await milestones(projectID: resolveProjectID(project))
    }

    func milestones(_ project: Int) async throws -> [OdooRecord] {
        try await milestones(projectID: project)
    }

    func createMilestone(_ project: String, name: String, deadline: Date) async throws -> Int {
        try await createMilestone(
            projectID: resolveProjectID(project), name: name, deadline: deadline
        )
    }

    func createMilestone(_ project: Int, name: String, deadline: Date) async throws -> Int {
        try await createMilestone(projectID: project, name: name, deadline: deadline)
    }

    private func milestones(projectID: Int) async throws -> [OdooRecord] {
        try await client.searchRead(
            model: "project.milestone",
            domain: [.array([.string("project_id"), .string("="), .integer(projectID)])],
            fields: [
                "id", "name", "project_id", "deadline", "is_reached", "reached_date",
                "is_deadline_exceeded",
            ],
            limit: nil,
            offset: 0,
            order: "deadline, id"
        )
    }

    private func createMilestone(projectID: Int, name: String, deadline: Date) async throws -> Int {
        try await client.create(model: "project.milestone", values: [
            "project_id": .integer(projectID),
            "name": .string(name),
            "deadline": .string(try OdooDateCodec.formatDate(deadline)),
        ], context: nil)
    }
}
