import Foundation
import XCTest
@testable import Vodoo

final class LiveIntegrationTests: XCTestCase {
    private func clientFromEnvironment() throws -> (OdooClient, Int) {
        let environment = ProcessInfo.processInfo.environment
        guard let urlText = environment["ODOO_URL"],
              let url = URL(string: urlText),
              let database = environment["ODOO_DATABASE"],
              let username = environment["ODOO_USERNAME"],
              let password = environment["ODOO_PASSWORD"],
              let versionText = environment["ODOO_MAJOR_VERSION"],
              let version = Int(versionText) else {
            throw XCTSkip("Odoo integration environment is not configured")
        }
        return (
            OdooClient(
                config: OdooConfig(
                    url: url,
                    database: database,
                    username: username,
                    password: password
                )
            ),
            version
        )
    }

    func testAuthenticationTransportAndGenericCRUD() async throws {
        let (client, version) = try clientFromEnvironment()
        let uid = try await client.getUID()
        XCTAssertGreaterThan(uid, 0)
        let dialect = try await client.transportDialect()
        XCTAssertEqual(dialect, version >= 19 ? .json2 : .jsonrpc)

        let partners = client.model("res.partner")
        let originalName = "Vodoo Swift Integration \(UUID().uuidString)"
        let partnerID = try await partners.create(["name": .string(originalName)])
        XCTAssertGreaterThan(partnerID, 0)

        do {
            let created = try await partners.read([partnerID], fields: ["id", "name"])
            XCTAssertEqual(created.first?["name"], .string(originalName))

            let updatedName = "\(originalName) Updated"
            let didWrite = try await partners.write(
                [partnerID],
                values: ["name": .string(updatedName)]
            )
            XCTAssertTrue(didWrite)
            let matches = try await partners.search(
                domain: [.array([.string("id"), .string("="), .integer(partnerID)])],
                limit: 1
            )
            XCTAssertEqual(matches, [partnerID])
            let names = try await partners.nameSearch(updatedName, limit: 5)
            XCTAssertTrue(names.contains { $0.id == partnerID })
        } catch {
            _ = try? await partners.unlink([partnerID])
            throw error
        }
        let didUnlink = try await partners.unlink([partnerID])
        XCTAssertTrue(didUnlink)
    }

    func testFeatureParityNamespacesAgainstLiveOdoo() async throws {
        let (client, _) = try clientFromEnvironment()
        let uid = try await client.getUID()
        let enterprise = ProcessInfo.processInfo.environment["ODOO_ENTERPRISE"] == "1"
        let suffix = UUID().uuidString
        var cleanup: [(String, Int)] = []

        do {
            let projectID = try await client.generic.create(
                model: "project.project", values: ["name": .string("Swift project \(suffix)")]
            )
            cleanup.append(("project.project", projectID))
            let resolvedProjectID = try await client.projects.resolveProjectID("Swift project \(suffix)")
            XCTAssertEqual(resolvedProjectID, projectID)

            let milestoneID = try await client.projects.createMilestone(
                projectID,
                name: "Swift milestone \(suffix)",
                deadline: try OdooDateCodec.parseDate("2027-01-31")
            )
            cleanup.insert(("project.milestone", milestoneID), at: 0)

            let taskID = try await client.tasks.create(
                "Swift task \(suffix)",
                projectID: projectID,
                options: CreateTaskOptions(description: "**Native Swift** task")
            )
            cleanup.insert(("project.task", taskID), at: 0)
            let task = try await client.tasks.get(taskID)
            XCTAssertEqual(task["name"], .string("Swift task \(suffix)"))
            let assignedMilestone = try await client.tasks.setMilestone(taskID, milestoneID: milestoneID)
            XCTAssertTrue(assignedMilestone)
            if enterprise {
                let scheduled = try await client.tasks.schedule(
                    taskID,
                    start: OdooDateCodec.parseDateTime("2027-01-02 03:04:05"),
                    end: OdooDateCodec.parseDate("2027-01-31")
                )
                XCTAssertTrue(scheduled)
            }

            let tagID = try await client.tasks.createTag("Swift tag \(suffix)", color: 3)
            cleanup.insert(("project.tags", tagID), at: 0)
            let addedTag = try await client.tasks.addTag(taskID, tagID: tagID)
            XCTAssertTrue(addedTag)

            let attachmentID = try await client.tasks.attach(
                taskID, data: Data([0, 1, 2, 255]), name: "swift-\(suffix).bin"
            )
            cleanup.insert(("ir.attachment", attachmentID), at: 0)
            let attachmentData = try await client.tasks.attachmentData(attachmentID)
            let commented = try await client.tasks.comment(
                taskID, message: .markdown("Swift comment \(suffix)"), options: MessageOptions(userID: uid)
            )
            XCTAssertEqual(attachmentData, Data([0, 1, 2, 255]))
            XCTAssertTrue(commented)

            let leadID = try await client.crm.create(
                "Swift opportunity \(suffix)", options: CreateCRMOptions(expectedRevenue: 1_000)
            )
            cleanup.insert(("crm.lead", leadID), at: 0)
            let lead = try await client.crm.get(leadID)
            XCTAssertEqual(lead["name"], .string("Swift opportunity \(suffix)"))
            let pipeline = try await client.crm.pipeline()
            XCTAssertTrue(pipeline.deals.contains { $0.id == leadID })

            if enterprise { _ = try await client.timer.list(days: 0, limit: 1) }
            _ = try await client.accountMoves.list(limit: 1)
            _ = try await client.activities.list(limit: 1)
            _ = try await client.security.getGroupIDs(["API Base"])
        } catch {
            for (model, id) in cleanup { _ = try? await client.unlink(model: model, ids: [id]) }
            throw error
        }
        for (model, id) in cleanup { _ = try? await client.unlink(model: model, ids: [id]) }
    }

    func testEnterpriseFeatureParityNamespacesAgainstLiveOdoo() async throws {
        guard ProcessInfo.processInfo.environment["ODOO_ENTERPRISE"] == "1" else {
            throw XCTSkip("Enterprise Odoo environment is not configured")
        }
        let (client, _) = try clientFromEnvironment()
        let uid = try await client.getUID()
        let suffix = UUID().uuidString
        var cleanup: [(String, Int)] = []

        do {
            let ticketID = try await client.helpdesk.create(
                "Swift ticket \(suffix)",
                options: CreateTicketOptions(description: "Created by Swift")
            )
            cleanup.append(("helpdesk.ticket", ticketID))
            let ticket = try await client.helpdesk.get(ticketID)
            XCTAssertEqual(ticket["name"], .string("Swift ticket \(suffix)"))
            let ticketCommented = try await client.helpdesk.comment(
                ticketID,
                message: .markdown("Swift ticket comment \(suffix)"),
                options: MessageOptions(userID: uid)
            )
            XCTAssertTrue(ticketCommented)
            let ticketAttachmentID = try await client.helpdesk.attach(
                ticketID, data: Data([72, 69, 76, 80]), name: "helpdesk-\(suffix).bin"
            )
            cleanup.insert(("ir.attachment", ticketAttachmentID), at: 0)
            let ticketBytes = try await client.helpdesk.attachmentData(ticketAttachmentID)
            XCTAssertEqual(ticketBytes, Data([72, 69, 76, 80]))

            let articleID = try await client.knowledge.create(
                "Swift article \(suffix)",
                options: CreateArticleOptions(body: "# Swift integration")
            )
            cleanup.insert(("knowledge.article", articleID), at: 0)
            let articleURL = try await client.knowledge.resolveURL(articleID)
            XCTAssertTrue(articleURL.absoluteString.contains(String(articleID)))

            let typeFields = try await client.fieldsGet(
                model: "documents.document", fields: ["type"], attributes: ["selection"]
            )
            let selection = typeFields["type"]?.objectValue?["selection"]
            let modern = selection?.arrayValue?.contains {
                $0.arrayValue?.first?.stringValue == "folder"
            } ?? (selection?.objectValue?["folder"] != nil)
            let folderModel = modern ? "documents.document" : "documents.folder"
            var folderValues: OdooRecord = ["name": .string("Swift folder \(suffix)")]
            if modern { folderValues["type"] = .string("folder") }
            let folderID = try await client.create(
                model: folderModel, values: folderValues, context: nil
            )
            cleanup.insert((folderModel, folderID), at: 0)
            let resolvedFolderID = try await client.documents.resolveFolder("Swift folder \(suffix)")
            XCTAssertEqual(resolvedFolderID, folderID)

            let documentID = try await client.documents.upload(
                data: Data([83, 87]), name: "swift-\(suffix).txt",
                options: DocumentUploadOptions(folderID: folderID)
            )
            cleanup.insert(("documents.document", documentID), at: 0)
            let document = try await client.documents.downloadFile(documentID)
            XCTAssertEqual(document.data, Data([83, 87]))
            XCTAssertEqual(document.name, "swift-\(suffix).txt")

            let timerProjectID = try await client.create(
                model: "project.project",
                values: [
                    "name": .string("Swift timer project \(suffix)"),
                    "allow_timesheets": .bool(true),
                ],
                context: nil
            )
            cleanup.insert(("project.project", timerProjectID), at: 0)
            let timerTaskID = try await client.tasks.create(
                "Swift timer task \(suffix)", projectID: timerProjectID
            )
            cleanup.insert(("project.task", timerTaskID), at: 0)
            let handle = try await client.timer.startTask(timerTaskID)
            let active = try await client.timer.active()
            XCTAssertTrue(active.contains {
                $0.source.kind == .task && $0.source.id == timerTaskID
            })
            try await handle.stop()
            let timesheetIDs = try await client.search(
                model: timesheetModel,
                domain: [.array([.string("task_id"), .string("="), .integer(timerTaskID)])],
                limit: nil, offset: 0, order: nil
            )
            for id in timesheetIDs { cleanup.insert((timesheetModel, id), at: 0) }
        } catch {
            for (model, id) in cleanup { _ = try? await client.unlink(model: model, ids: [id]) }
            throw error
        }
        for (model, id) in cleanup { _ = try? await client.unlink(model: model, ids: [id]) }
    }
}
