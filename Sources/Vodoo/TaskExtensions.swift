import Foundation

public struct CreateTaskOptions: Sendable, Equatable {
    public var description: RichText?
    public var userIDs: [Int]?
    public var tagIDs: [Int]?
    public var parentID: Int?
    public var extraFields: OdooRecord

    public init(
        description: RichText? = nil,
        userIDs: [Int]? = nil,
        tagIDs: [Int]? = nil,
        parentID: Int? = nil,
        extraFields: OdooRecord = [:]
    ) {
        self.description = description
        self.userIDs = userIDs
        self.tagIDs = tagIDs
        self.parentID = parentID
        self.extraFields = extraFields
    }
}

public extension GeneratedTaskNamespace {
    func create(
        _ name: String,
        projectID: Int,
        options: CreateTaskOptions = CreateTaskOptions()
    ) async throws -> Int {
        var values = options.extraFields
        values["name"] = .string(name)
        values["project_id"] = .integer(projectID)
        if let description = options.description {
            values["description"] = .string(OdooContent.richTextToHTML(description))
        }
        if let ids = options.userIDs, !ids.isEmpty {
            values["user_ids"] = .array([Command.set(ids).wireValue])
        }
        if let ids = options.tagIDs, !ids.isEmpty {
            values["tag_ids"] = .array([Command.set(ids).wireValue])
        }
        if let parentID = options.parentID, parentID != 0 { values["parent_id"] = .integer(parentID) }
        return try await client.create(
            model: model,
            values: values,
            context: ["default_project_id": .integer(projectID)]
        )
    }

    func setMilestone(_ taskID: Int, milestoneID: Int) async throws -> Bool {
        let tasks = try await client.read(model: "project.task", ids: [taskID], fields: ["project_id"])
        guard let task = tasks.first else {
            throw VodooError.recordNotFound(model: "project.task", id: taskID)
        }
        let milestones = try await client.read(
            model: "project.milestone", ids: [milestoneID], fields: ["project_id"]
        )
        guard let milestone = milestones.first else {
            throw VodooError.recordNotFound(model: "project.milestone", id: milestoneID)
        }
        guard let taskProjectID = relationID(task["project_id"]),
              let milestoneProjectID = relationID(milestone["project_id"]) else {
            throw VodooError.operation("Task and milestone must both belong to a project")
        }
        guard taskProjectID == milestoneProjectID else {
            throw VodooError.operation(
                "Task \(taskID) and milestone \(milestoneID) belong to different projects"
            )
        }
        return try await client.write(
            model: "project.task", ids: [taskID], values: ["milestone_id": .integer(milestoneID)]
        )
    }

    func addDependencies(_ taskID: Int, dependencyIDs: [Int]) async throws -> Bool {
        try await set(taskID, values: [
            "depend_on_ids": .array(dependencyIDs.map { Command.link($0).wireValue }),
        ])
    }

    func clearDependencies(_ taskID: Int) async throws -> Bool {
        try await set(taskID, values: ["depend_on_ids": .array([Command.clear.wireValue])])
    }

    func schedule(_ taskID: Int, start: Date, end: Date) async throws -> Bool {
        try await set(taskID, values: [
            "planned_date_begin": .string(try OdooDateCodec.formatDateTime(start)),
            "date_deadline": .string(try OdooDateCodec.formatDate(end)),
        ])
    }

    func createTag(_ name: String, color: Int? = nil) async throws -> Int {
        var values: OdooRecord = ["name": .string(name)]
        if let color { values["color"] = .integer(color) }
        return try await client.create(model: "project.tags", values: values, context: nil)
    }

    func deleteTag(_ tagID: Int) async throws -> Bool {
        try await client.unlink(model: "project.tags", ids: [tagID])
    }
}
