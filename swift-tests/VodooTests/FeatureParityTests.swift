import Foundation
import XCTest
@testable import Vodoo

private struct FeatureCall: Sendable, Equatable {
    let model: String
    let method: String
    let args: [JSONValue]
    let kwargs: OdooRecord?
}

private enum FeatureResponse: Sendable {
    case value(JSONValue)
    case failure(VodooError)
}

private actor FeatureTransport: OdooTransportProtocol {
    nonisolated let dialect: TransportDialect
    private var responses: [FeatureResponse]
    private var calls: [FeatureCall] = []
    private let uid: Int

    init(
        _ values: [JSONValue] = [],
        dialect: TransportDialect = .json2,
        uid: Int = 7
    ) {
        responses = values.map(FeatureResponse.value)
        self.dialect = dialect
        self.uid = uid
    }

    init(
        responses: [FeatureResponse],
        dialect: TransportDialect = .json2,
        uid: Int = 7
    ) {
        self.responses = responses
        self.dialect = dialect
        self.uid = uid
    }

    func getUID() async throws -> Int { uid }

    func execute(
        model: String,
        method: String,
        args: [JSONValue],
        kwargs: OdooRecord?
    ) async throws -> JSONValue {
        calls.append(FeatureCall(model: model, method: method, args: args, kwargs: kwargs))
        guard !responses.isEmpty else { throw VodooError.invalidResponse("No response queued") }
        switch responses.removeFirst() {
        case let .value(value): return value
        case let .failure(error): throw error
        }
    }

    func recorded() -> [FeatureCall] { calls }
}

private actor TransportInitializationCounter {
    private(set) var count = 0

    func initialize() async throws -> any OdooTransportProtocol {
        count += 1
        try await Task.sleep(nanoseconds: 20_000_000)
        return FeatureTransport(dialect: .json2, uid: 7)
    }
}

private actor FailingOnceTransportInitializationCounter {
    private(set) var count = 0

    func initialize() async throws -> any OdooTransportProtocol {
        count += 1
        try await Task.sleep(nanoseconds: 20_000_000)
        if count == 1 { throw VodooError.invalidResponse("expected initialization failure") }
        return FeatureTransport(dialect: .json2, uid: 7)
    }
}

private func retryAfterInitializationFailure(_ client: OdooClient) async throws -> Int {
    do {
        _ = try await client.getUID()
        throw VodooError.invalidResponse("expected first initialization to fail")
    } catch VodooError.invalidResponse(let message)
        where message == "expected initialization failure"
    {
        return try await client.getUID()
    }
}

private func featureClient(
    _ transport: FeatureTransport,
    defaultUserID: Int? = nil
) -> OdooClient {
    OdooClient(
        config: OdooConfig(
            url: URL(string: "https://odoo.example.test/")!,
            database: "fixture",
            username: "user",
            password: "key",
            defaultUserID: defaultUserID
        ),
        transport: transport
    )
}

private func row(_ values: OdooRecord) -> JSONValue { .object(values) }
private func rows(_ values: [OdooRecord]) -> JSONValue { .array(values.map(JSONValue.object)) }

final class DomainNamespaceCompatibilityTests: XCTestCase {
    func testUninitializedAutoClientUsesLegacyRecordURLWithoutIO() throws {
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test/")),
                database: "fixture",
                username: "user",
                password: "key"
            )
        )

        XCTAssertEqual(
            client.projects.url(7).absoluteString,
            "https://odoo.example.test/web#id=7&model=project.project&view_type=form"
        )
    }

    func testConcurrentFirstUseSharesTransportInitialization() async throws {
        let counter = TransportInitializationCounter()
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test/")),
                database: "fixture",
                username: "user",
                password: "key"
            ),
            transportInitializer: { try await counter.initialize() }
        )

        async let firstUID = client.getUID()
        async let secondUID = client.getUID()
        let uids = try await [firstUID, secondUID]

        let initializationCount = await counter.count
        XCTAssertEqual(uids, [7, 7])
        XCTAssertEqual(initializationCount, 1)
        XCTAssertEqual(
            client.projects.url(7).absoluteString,
            "https://odoo.example.test/odoo/project.project/7"
        )
    }

    func testConcurrentInitializationFailureCanRetryImmediately() async throws {
        let counter = FailingOnceTransportInitializationCounter()
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test/")),
                database: "fixture",
                username: "user",
                password: "key"
            ),
            transportInitializer: { try await counter.initialize() }
        )

        async let firstUID = retryAfterInitializationFailure(client)
        async let secondUID = retryAfterInitializationFailure(client)
        let uids = try await [firstUID, secondUID]
        let initializationCount = await counter.count

        XCTAssertEqual(uids, [7, 7])
        XCTAssertEqual(initializationCount, 2)
        XCTAssertEqual(
            client.projects.url(7).absoluteString,
            "https://odoo.example.test/odoo/project.project/7"
        )
    }

    func testInitializerDefaultsDateFieldsForSourceCompatibility() {
        let namespace = DomainNamespace(
            client: featureClient(FeatureTransport()),
            model: "x.fixture",
            defaultFields: [],
            defaultDetailFields: nil,
            tagModel: nil,
            capabilities: [],
            availability: NamespaceAvailability(
                module: "base", editions: ["community"], minVersion: 17
            )
        )

        XCTAssertEqual(namespace.dateFields, [:])
    }
}

final class ContentFeatureTests: XCTestCase {
    func testMarkdownHeadingsListsAndInlineFormatting() {
        XCTAssertEqual(
            OdooContent.markdownToHTML("# Title\n\n- one\n- **two**"),
            "<h1>Title</h1>\n<ul>\n<li>one</li>\n<li><strong>two</strong></li>\n</ul>"
        )
        XCTAssertEqual(OdooContent.markdownToHTML("`code` and *em*"), "<p><code>code</code> and <em>em</em></p>")
    }

    func testMarkdownEscapesHTMLAndUnsafeLinks() {
        XCTAssertEqual(
            OdooContent.markdownToHTML("<img src=x>"),
            "<p>&lt;img src=x&gt;</p>"
        )
        XCTAssertEqual(
            OdooContent.markdownToHTML("[click](javascript:alert(1))"),
            "<p>[click](javascript:alert(1))</p>"
        )
    }

    func testExplicitHTMLAndPlainTextModes() {
        XCTAssertEqual(OdooContent.richTextToHTML(.html("<b>ok</b>")), "<b>ok</b>")
        XCTAssertEqual(
            OdooContent.richTextToHTML(.plain("**literal** <b>text</b>")),
            "<p>**literal** &lt;b&gt;text&lt;/b&gt;</p>"
        )
        XCTAssertEqual(
            OdooContent.richTextToHTML(.markdown("**literal**"), markdownByDefault: false),
            "<p>**literal**</p>"
        )
    }
}

final class DomainFeatureTests: XCTestCase {
    func testCommentsResolveAuthorSubtypeAndRenderMarkdown() async throws {
        let transport = FeatureTransport([
            rows([["partner_id": .array([.integer(8), .string("Ada")])]]),
            rows([["res_id": .integer(4)]]),
            .integer(91),
        ])
        let client = featureClient(transport, defaultUserID: 7)
        let didComment = try await client.tasks.comment(2, message: "**Done**")
        XCTAssertTrue(didComment)
        let calls = await transport.recorded()
        XCTAssertEqual(calls[1].model, "ir.model.data")
        XCTAssertEqual(calls[1].args.first, .array([
            .array([.string("module"), .string("="), .string("mail")]),
            .array([.string("name"), .string("="), .string("mt_comment")]),
        ]))
        XCTAssertEqual(calls.last?.model, "mail.message")
        XCTAssertEqual(calls.last?.args.first?.objectValue?["body"], .string("<p><strong>Done</strong></p>"))
        XCTAssertEqual(calls.last?.args.first?.objectValue?["author_id"], .integer(8))
    }

    func testMarkdownFalseTreatsStringLiteralAsPlainText() async throws {
        let transport = FeatureTransport([
            rows([["partner_id": .integer(8)]]), rows([["res_id": .integer(4)]]), .integer(93),
        ])
        let client = featureClient(transport, defaultUserID: 7)
        _ = try await client.tasks.comment(
            2, message: "**literal** <b>text</b>", options: MessageOptions(markdown: false)
        )
        let values = await transport.recorded().last?.args.first?.objectValue
        XCTAssertEqual(values?["body"], .string("<p>**literal** &lt;b&gt;text&lt;/b&gt;</p>"))
    }

    func testNotesUseNotificationSubtype() async throws {
        let transport = FeatureTransport([
            rows([["partner_id": .integer(8)]]), rows([["res_id": .integer(5)]]), .integer(92),
        ])
        let client = featureClient(transport, defaultUserID: 7)
        let noteID = try await client.tasks.noteWithID(2, message: .html("<b>Note</b>"))
        XCTAssertEqual(noteID, 92)
        let values = await transport.recorded().last?.args.first?.objectValue
        XCTAssertEqual(values?["message_type"], .string("notification"))
        XCTAssertEqual(values?["subtype_id"], .integer(5))
    }

    func testMessagingRequiresPositiveStableSubtypeExternalID() async {
        let invalidSubtypeRows: [JSONValue] = [
            rows([]), rows([["res_id": .integer(0)]]), rows([["res_id": .integer(-1)]]),
            rows([["res_id": .bool(false)]]),
        ]
        for subtypeRows in invalidSubtypeRows {
            let client = featureClient(
                FeatureTransport([rows([["partner_id": .integer(8)]]), subtypeRows]),
                defaultUserID: 7
            )
            do {
                _ = try await client.tasks.comment(2, message: "x")
                XCTFail("Expected missing subtype")
            } catch let error as VodooError {
                XCTAssertEqual(error, .recordNotFound(model: "mail.message.subtype", id: 0))
            } catch { XCTFail("Unexpected error: \(error)") }
        }
    }

    func testMessagingRequiresDefaultUser() async {
        let client = featureClient(FeatureTransport())
        do {
            _ = try await client.tasks.comment(2, message: "x")
            XCTFail("Expected configuration error")
        } catch let error as VodooError {
            XCTAssertEqual(error, .configuration("No default user ID configured"))
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testMessagesAndTagsUseNamespaceMetadata() async throws {
        let transport = FeatureTransport([
            rows([["id": .integer(1), "body": .string("Hi")]]),
            rows([["id": .integer(3), "name": .string("Backend")]]),
        ])
        let client = featureClient(transport)
        let messages = try await client.tasks.messages(2)
        let tags = try await client.tasks.tags()
        XCTAssertEqual(messages.count, 1)
        XCTAssertEqual(tags.first?["name"], .string("Backend"))
        let calls = await transport.recorded()
        XCTAssertEqual(calls[0].model, "mail.message")
        XCTAssertEqual(calls[1].model, "project.tags")
    }

    func testTagsFailForNamespacesWithoutTagModels() async {
        let client = featureClient(FeatureTransport())
        do {
            _ = try await client.projects.tags()
            XCTFail("Expected operation error")
        } catch let error as VodooError {
            XCTAssertEqual(error, .operation("No tag model defined for project.project"))
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testAddTagPreservesExistingTagsAndAvoidsDuplicateWrites() async throws {
        let transport = FeatureTransport([
            rows([["tag_ids": .array([.integer(2)])]]), .bool(true),
            rows([["tag_ids": .array([.integer(2), .integer(3)])]]),
        ])
        let client = featureClient(transport)
        let firstAdd = try await client.tasks.addTag(1, tagID: 3)
        let duplicateAdd = try await client.tasks.addTag(1, tagID: 3)
        XCTAssertTrue(firstAdd)
        XCTAssertTrue(duplicateAdd)
        let calls = await transport.recorded()
        XCTAssertEqual(calls.filter { $0.method == "write" }.count, 1)
        XCTAssertEqual(
            calls[1].args[1].objectValue?["tag_ids"],
            .array([Command.set([2, 3]).wireValue])
        )
    }

    func testAttachAndReadAttachmentData() async throws {
        let transport = FeatureTransport([
            .integer(11),
            rows([["name": .string("x.txt"), "datas": .string("SGk=")]]),
        ])
        let client = featureClient(transport)
        let id = try await client.tasks.attach(
            2, data: Data("Hi".utf8), name: "x.txt",
            options: AttachmentOptions(mimetype: "text/plain")
        )
        XCTAssertEqual(id, 11)
        let downloaded = try await client.tasks.attachmentData(11)
        XCTAssertEqual(downloaded, Data("Hi".utf8))
    }

    func testAllAttachmentDataSkipsUnreadableRecordsAndFiltersExtensions() async throws {
        let transport = FeatureTransport([
            rows([
                ["id": .integer(1), "name": .string("one.PDF"), "mimetype": .string("application/pdf")],
                ["id": .integer(2), "name": .string("two.txt")],
            ]),
            rows([["name": .string("one.PDF"), "datas": .string("QQ==")]]),
            rows([["name": .string("two.txt"), "datas": .bool(false), "file_size": .integer(9)]]),
        ])
        let values = try await featureClient(transport).tasks.download(4, extension: ".pdf")
        XCTAssertEqual(values, [AttachmentData(
            id: 1, name: "one.PDF", data: Data([65]), mimetype: "application/pdf"
        )])
    }
}

final class TaskProjectKnowledgeFeatureTests: XCTestCase {
    func testTaskCreateUsesMarkdownCommandsContextAndTypedPrecedence() async throws {
        let transport = FeatureTransport([.integer(21)])
        let client = featureClient(transport)
        let id = try await client.tasks.create(
            "Deploy",
            projectID: 7,
            options: CreateTaskOptions(
                description: "**Ship it**", userIDs: [2], tagIDs: [3], parentID: 4,
                extraFields: ["name": .string("ignored"), "project_id": .integer(999), "priority": .string("1")]
            )
        )
        XCTAssertEqual(id, 21)
        let call = await transport.recorded().first
        XCTAssertEqual(call?.args.first?.objectValue?["name"], .string("Deploy"))
        XCTAssertEqual(call?.args.first?.objectValue?["description"], .string("<p><strong>Ship it</strong></p>"))
        XCTAssertEqual(call?.kwargs?["context"]?.objectValue?["default_project_id"], .integer(7))
    }

    func testTaskMilestoneValidationAndAssignment() async throws {
        let transport = FeatureTransport([
            rows([["project_id": .array([.integer(7), .string("P")])]]),
            rows([["project_id": .integer(7)]]), .bool(true),
        ])
        let assigned = try await featureClient(transport).tasks.setMilestone(2, milestoneID: 9)
        XCTAssertTrue(assigned)
    }

    func testTaskMilestoneRejectsDifferentProjects() async {
        let transport = FeatureTransport([
            rows([["project_id": .integer(7)]]), rows([["project_id": .integer(8)]])
        ])
        do {
            _ = try await featureClient(transport).tasks.setMilestone(2, milestoneID: 9)
            XCTFail("Expected project mismatch")
        } catch let error as VodooError {
            XCTAssertEqual(
                error, .operation("Task 2 and milestone 9 belong to different projects")
            )
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testTaskDependenciesScheduleAndTags() async throws {
        let transport = FeatureTransport([.bool(true), .bool(true), .bool(true), .integer(88), .bool(true)])
        let tasks = featureClient(transport).tasks
        let added = try await tasks.addDependencies(2, dependencyIDs: [3, 4])
        let cleared = try await tasks.clearDependencies(2)
        let scheduled = try await tasks.schedule(
            2,
            start: try OdooDateCodec.parseDateTime("2026-04-05 06:07:08"),
            end: try OdooDateCodec.parseDate("2026-05-06")
        )
        let tagID = try await tasks.createTag("Backend", color: 0)
        let deleted = try await tasks.deleteTag(88)
        XCTAssertTrue(added)
        XCTAssertTrue(cleared)
        XCTAssertTrue(scheduled)
        XCTAssertEqual(tagID, 88)
        XCTAssertTrue(deleted)
    }

    func testProjectResolvesExactNameAndRejectsAmbiguity() async throws {
        let transport = FeatureTransport([
            rows([["id": .integer(7), "name": .string("Straße")]]),
            rows([
                ["id": .integer(7), "name": .string("Same")],
                ["id": .integer(8), "name": .string("same")],
            ]),
        ])
        let projects = featureClient(transport).projects
        let projectID = try await projects.resolveProjectID("STRASSE")
        XCTAssertEqual(projectID, 7)
        do {
            _ = try await projects.resolveProjectID("Same")
            XCTFail("Expected ambiguity")
        } catch let error as VodooError {
            XCTAssertEqual(error, .operation("Project name 'Same' is ambiguous; use a project ID"))
        }
    }

    func testProjectAndMilestoneDatesDecodeToNativeValues() async throws {
        let transport = FeatureTransport([
            rows([[
                "id": .integer(7), "date_start": .string("2026-01-02"),
                "write_date": .string("2026-01-02 03:04:05"),
            ]]),
            rows([[
                "id": .integer(4), "name": .string("Beta"),
                "deadline": .string("2026-07-08"), "reached_date": .string("2026-07-09"),
            ]]),
            .integer(5),
        ])
        let projects = featureClient(transport).projects
        let project = try await projects.get(7)
        let milestones = try await projects.milestones(7)
        let createdID = try await projects.createMilestone(
            7, name: "Launch", deadline: OdooDateCodec.parseDate("2026-07-08")
        )
        XCTAssertEqual(
            try project["date_start"]?.dateValue.map(OdooDateCodec.formatDate), "2026-01-02"
        )
        XCTAssertEqual(
            try project["write_date"]?.dateValue.map(OdooDateCodec.formatDateTime),
            "2026-01-02 03:04:05"
        )
        XCTAssertEqual(
            try milestones.first?["deadline"]?.dateValue.map(OdooDateCodec.formatDate),
            "2026-07-08"
        )
        XCTAssertEqual(createdID, 5)
    }

    func testKnowledgeCreatesMarkdownWithTypedPrecedence() async throws {
        let transport = FeatureTransport([.integer(44)])
        let knowledge = featureClient(transport).knowledge
        let articleID = try await knowledge.create(
            "Runbook",
            options: CreateArticleOptions(
                body: "# Deploy", parentID: 2, category: "workspace", icon: "📘",
                extraFields: ["name": .string("ignored")]
            )
        )
        XCTAssertEqual(articleID, 44)
        let values = await transport.recorded().first?.args.first?.objectValue
        XCTAssertEqual(values?["name"], .string("Runbook"))
        XCTAssertEqual(values?["body"], .string("<h1>Deploy</h1>"))
    }

    func testKnowledgeResolvesServerAndFallbackURLs() async throws {
        let transport = FeatureTransport([
            rows([["article_url": .string("https://kb.example.test/a")]]),
            rows([["article_url": .bool(false)]]),
        ])
        let knowledge = featureClient(transport).knowledge
        let serverURL = try await knowledge.resolveURL(1)
        let fallbackURL = try await knowledge.resolveURL(2)
        XCTAssertEqual(serverURL.absoluteString, "https://kb.example.test/a")
        XCTAssertEqual(
            fallbackURL.absoluteString,
            "https://odoo.example.test/odoo/knowledge.article/2"
        )
    }
}

final class CRMAndSimpleNamespaceFeatureTests: XCTestCase {
    func testActivityAndAccountMoveDomainBuilders() {
        XCTAssertEqual(
            buildActivityDomain(ActivityDomainOptions(model: "crm.lead", user: "Ada", activityType: "Call")).count,
            3
        )
        let domain = buildAccountMoveDomain(AccountMoveDomainOptions(
            search: "INV", companyID: 2, state: "posted", year: 2026
        ))
        XCTAssertEqual(domain.prefix(3), [.string("|"), .string("|"), .string("|")])
        XCTAssertTrue(domain.contains(.array([.string("date"), .string(">="), .string("2026-01-01")])))
    }

    func testActivityDoneChecksStateAndExecutesAction() async throws {
        let transport = FeatureTransport([rows([["active": .bool(true)]]), .bool(true)])
        let result = try await featureClient(transport).activities.done(4)
        XCTAssertEqual(result, .bool(true))
        let calls = await transport.recorded()
        XCTAssertEqual(calls.last?.method, "action_done")
    }

    func testActivityDoneRejectsInactiveRecords() async {
        let transport = FeatureTransport([rows([["active": .bool(false)]])])
        do {
            _ = try await featureClient(transport).activities.done(4)
            XCTFail("Expected already-done error")
        } catch let error as VodooError {
            XCTAssertEqual(error, .operation("Activity 4 is already done"))
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testCRMCreateUsesTypedPrecedenceAndCommands() async throws {
        let transport = FeatureTransport([.integer(19)])
        let crm = featureClient(transport).crm
        let leadID = try await crm.create("Renewal", options: CreateCRMOptions(
            expectedRevenue: 5_000, teamID: 4, tagIDs: [3],
            extraFields: ["name": .string("ignored"), "priority": .string("2")]
        ))
        XCTAssertEqual(leadID, 19)
        let values = await transport.recorded().first?.args.first?.objectValue
        XCTAssertEqual(values?["name"], .string("Renewal"))
        XCTAssertEqual(values?["tag_ids"], .array([Command.set([3]).wireValue]))
    }

    func testPipelineSummaryAggregatesDealsDeterministically() throws {
        let today = try OdooDateCodec.parseDateTime("2026-01-02 00:00:00")
        let summary = try buildPipelineSummary(
            deals: [[
                "id": .integer(1), "name": .string("Renewal"),
                "stage_id": .array([.integer(2), .string("Qualified")]),
                "expected_revenue": .number(1_000), "probability": .number(25),
                "create_date": .string("2026-01-01 00:00:00"),
                "partner_id": .array([.integer(4), .string("Acme")]),
                "user_id": .array([.integer(5), .string("Ada")]),
            ]],
            stages: [["id": .integer(2), "name": .string("Qualified")]],
            team: "Direct", today: today
        )
        XCTAssertEqual(summary.totals, PipelineTotals(deals: 1, revenue: 1_000, weighted: 250))
        XCTAssertEqual(summary.stages.first?.averageAgeDays, 1)
        XCTAssertEqual(summary.deals.first?.partner, "Acme")
    }

    func testPipelineUsesPythonHalfEvenRounding() throws {
        let date = try OdooDateCodec.parseDateTime("2026-01-02 00:00:00")
        let summary = try buildPipelineSummary(
            deals: [[
                "id": .integer(1), "stage_id": .integer(2),
                "expected_revenue": .number(2.675), "probability": .number(100),
                "create_date": .string("2026-01-02 00:00:00"),
            ]],
            stages: [["id": .integer(2), "name": .string("New")]],
            today: date
        )
        XCTAssertEqual(summary.totals.weighted, 2.67)
    }

    func testPipelineHealthFlagsCoverAllRules() throws {
        let today = try OdooDateCodec.parseDateTime("2026-01-01 00:00:00")
        let summary = try buildPipelineSummary(
            deals: [[
                "id": .integer(1), "name": .string("Unowned"), "stage_id": .integer(3),
                "expected_revenue": .integer(0), "probability": .integer(0),
                "create_date": .string("2025-01-01 00:00:00"),
            ]],
            stages: [
                ["id": .integer(2), "name": .string("New")],
                ["id": .integer(3), "name": .string("Qualified")],
            ],
            today: today
        )
        XCTAssertEqual(
            computeHealthFlags(summary).map(\.rule),
            ["Zero probability", "No partner", "No salesperson", "Stale deal"]
        )
    }

    func testPipelineFetchesDealsAndStages() async throws {
        let transport = FeatureTransport([
            rows([["id": .integer(1), "stage_id": .integer(2), "create_date": .string("2026-01-01 00:00:00")]]),
            rows([["id": .integer(2), "name": .string("New")]]),
        ])
        let summary = try await featureClient(transport).crm.pipeline(team: "Direct")
        XCTAssertEqual(summary.team, "Direct")
        let calls = await transport.recorded()
        XCTAssertEqual(calls[0].kwargs?["limit"], .integer(0))
        XCTAssertEqual(calls[1].model, "crm.stage")
    }
}


final class DocumentFeatureTests: XCTestCase {
    func testModernFoldersAndStableTree() async throws {
        let transport = FeatureTransport([
            .object(["type": .object(["selection": .array([
                .array([.string("binary"), .string("File")]),
                .array([.string("folder"), .string("Folder")]),
            ])])]),
            rows([
                ["id": .integer(3), "name": .string("Child"), "folder_id": .array([.integer(2), .string("Root")])],
                ["id": .integer(2), "name": .string("Root"), "folder_id": .bool(false)],
            ]),
        ])
        let folders = try await featureClient(transport).documents.folders(limit: nil, tree: true)
        XCTAssertEqual(folders.map(\.id), [2, 3])
        XCTAssertEqual(folders.last?.path, "Root / Child")
        XCTAssertEqual(folders.last?.depth, 1)
    }

    func testFolderTreeTerminatesCyclesDeterministically() {
        let values = orderDocumentFolderTree([
            DocumentFolder(id: 2, name: "Cycle B", parentFolder: .integer(1)),
            DocumentFolder(id: 1, name: "Cycle A", parentFolder: .integer(2)),
        ])
        XCTAssertEqual(values.map(\.id), [1, 2])
        XCTAssertEqual(values.map(\.depth), [0, 1])
    }

    func testFolderResolutionAcceptsIDsAndRejectsAmbiguousNames() async throws {
        let documents = featureClient(FeatureTransport()).documents
        let direct = try await documents.resolveFolder("9")
        XCTAssertEqual(direct, 9)

        let transport = FeatureTransport([
            .object(["type": .object(["selection": .array([.array([.string("binary")])])])]),
            rows([["id": .integer(4)], ["id": .integer(5)]]),
        ])
        do {
            _ = try await featureClient(transport).documents.resolveFolder("Shared")
            XCTFail("Expected ambiguous folder")
        } catch let error as VodooError {
            XCTAssertEqual(
                error,
                .operation("Multiple documents.folder records match 'Shared'; use a numeric ID")
            )
        }
    }

    func testDocumentUploadUsesBinaryCommandsAndMimetype() async throws {
        let transport = FeatureTransport([.integer(44)])
        let documents = featureClient(transport).documents
        let id = try await documents.upload(
            data: Data([1, 2, 3]), name: "report.pdf",
            options: DocumentUploadOptions(folderID: 9, tags: [5, 6], owner: 7)
        )
        XCTAssertEqual(id, 44)
        let values = await transport.recorded().first?.args.first?.objectValue
        XCTAssertEqual(values?["datas"], .string("AQID"))
        XCTAssertEqual(values?["mimetype"], .string("application/pdf"))
        XCTAssertEqual(values?["tag_ids"], .array([Command.set([5, 6]).wireValue]))
    }

    func testDocumentDownloadSanitizesFilenamesAndSupportsEmptyFiles() async throws {
        let transport = FeatureTransport([
            rows([["name": .string("../../CON.txt "), "type": .string("binary"), "datas": .string("SGk=")]]),
            rows([["name": .string(""), "type": .string("binary"), "datas": .bool(false), "file_size": .integer(0)]]),
        ])
        let documents = featureClient(transport).documents
        let first = try await documents.downloadFile(8)
        let second = try await documents.downloadFile(12)
        XCTAssertEqual(first.name, "_CON.txt")
        XCTAssertEqual(first.data, Data("Hi".utf8))
        XCTAssertEqual(second.name, "document_12")
        XCTAssertTrue(second.data.isEmpty)
    }

    func testDocumentUploadRequiresOneFolderSelector() async {
        let documents = featureClient(FeatureTransport()).documents
        do {
            _ = try await documents.upload(
                data: Data(), name: "x.txt",
                options: DocumentUploadOptions(folder: 1, folderID: 1)
            )
            XCTFail("Expected folder validation")
        } catch let error as VodooError {
            XCTAssertEqual(error, .operation("Specify exactly one of folder or folderID"))
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testSafeDocumentFilenameHandlesReservedAndTraversalNames() {
        XCTAssertEqual(safeDocumentFilename("../NUL", documentID: 3), "_NUL")
        XCTAssertEqual(safeDocumentFilename("../bad?.txt", documentID: 3), "bad_.txt")
    }
}

final class GenericAndClientFeatureTests: XCTestCase {
    func testUnboundGenericNamespaceForwardsEveryOperation() async throws {
        let transport = FeatureTransport([
            .integer(8), .bool(true), .bool(true), rows([["id": .integer(8)]]),
            .array([.integer(8), .string("Acme")]),
        ])
        let generic = featureClient(transport).generic
        let created = try await generic.create(model: "res.partner", values: ["name": .string("Acme")])
        let updated = try await generic.update(model: "res.partner", recordID: 8, values: ["phone": .string("+1")])
        let deleted = try await generic.delete(model: "res.partner", recordID: 8)
        let records = try await generic.search(model: "res.partner")
        let result = try await generic.call(model: "res.partner", method: "name_get", args: [.array([.integer(8)])])
        XCTAssertEqual(created, 8)
        XCTAssertTrue(updated)
        XCTAssertTrue(deleted)
        XCTAssertEqual(records.first?["id"], .integer(8))
        XCTAssertEqual(result, .array([.integer(8), .string("Acme")]))
    }

    func testExecuteWithUserContextMergesExistingContext() async throws {
        let transport = FeatureTransport([.bool(true)])
        let result = try await featureClient(transport).executeWithUserContext(
            model: "res.partner", method: "write", userID: 9,
            kwargs: ["context": .object(["lang": .string("en_US")])]
        )
        XCTAssertEqual(result, .bool(true))
        let context = await transport.recorded().first?.kwargs?["context"]?.objectValue
        XCTAssertEqual(context?["lang"], .string("en_US"))
        XCTAssertEqual(context?["sudo_user_id"], .integer(9))
    }

    func testFieldsGetForwardsFieldAndAttributeFilters() async throws {
        let transport = FeatureTransport([.object(["name": .object(["type": .string("char")])])])
        let fields = try await featureClient(transport).fieldsGet(
            model: "res.partner", fields: ["name"], attributes: ["type"]
        )
        XCTAssertEqual(fields["name"]?.objectValue?["type"], .string("char"))
        let call = await transport.recorded().first
        XCTAssertEqual(call?.args, [.array([.string("name")])])
        XCTAssertEqual(call?.kwargs?["attributes"], .array([.string("type")]))
    }
}

final class SecurityFeatureTests: XCTestCase {
    func testGeneratedSecurityCatalogHasAllProfiles() {
        XCTAssertEqual(
            SECURITY_GROUP_DEFINITIONS.map(\.name),
            ["API Mail Gateway", "API Base", "API CRM", "API Project", "API Knowledge", "API Helpdesk"]
        )
    }

    func testCreateUserUsesOdoo19GroupField() async throws {
        let transport = FeatureTransport([
            .object(["group_ids": .object(["type": .string("many2many")])]), .integer(71),
        ])
        let user = try await featureClient(transport).security.createUser(
            name: "API Bot", login: "bot@example.com", password: "not-generated"
        )
        XCTAssertEqual(user, CreatedUser(userID: 71, password: "not-generated"))
        let values = await transport.recorded().last?.args.first?.objectValue
        XCTAssertEqual(values?["group_ids"], .array([Command.set([]).wireValue]))
    }

    func testAssignRemovesDefaultsAndFallsBackToLegacyGroupField() async throws {
        let transport = FeatureTransport([
            rows([["res_id": .integer(10)]]), rows([["res_id": .integer(11)]]),
            .object([:]), .bool(true),
        ])
        try await featureClient(transport).security.assign(userID: 5, groupIDs: [20, 21])
        let values = await transport.recorded().last?.args[1].objectValue
        XCTAssertEqual(values?["groups_id"], .array([
            Command.unlink(10).wireValue, Command.unlink(11).wireValue,
            Command.link(20).wireValue, Command.link(21).wireValue,
        ]))
    }

    func testResolveUsersGroupsPasswordsAndLookups() async throws {
        let transport = FeatureTransport([
            .array([.integer(33)]), .array([.integer(40)]), .array([]), .bool(true),
            .object([:]), rows([["id": .integer(33), "login": .string("bot")]]),
        ])
        let security = featureClient(transport).security
        let userID = try await security.resolveUser(login: "bot")
        let groups = try await security.getGroupIDs(["API Base", "Missing"])
        let password = try await security.setPassword(33, password: "changed")
        let user = try await security.getUser(33)
        XCTAssertEqual(userID, 33)
        XCTAssertEqual(groups.groupIDs, ["API Base": 40])
        XCTAssertEqual(groups.warnings, ["Group 'Missing' not found"])
        XCTAssertEqual(password, "changed")
        XCTAssertEqual(user["login"], .string("bot"))
    }

    func testSecurityValidatesUserLookupInputs() async {
        do {
            _ = try await featureClient(FeatureTransport()).security.resolveUser()
            XCTFail("Expected input validation")
        } catch let error as VodooError {
            XCTAssertEqual(error, .operation("Provide userID or login"))
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testCreateGroupsProvisionsAllAvailableAccessAndRules() async throws {
        var responses: [JSONValue] = []
        var nextID = 100
        for group in SECURITY_GROUP_DEFINITIONS {
            responses.append(.array([]))
            responses.append(.integer(nextID)); nextID += 1
            for _ in group.access {
                responses.append(.array([.integer(nextID)])); nextID += 1
                responses.append(.array([]))
                responses.append(.integer(nextID)); nextID += 1
            }
            for _ in group.rules {
                responses.append(.array([.integer(nextID)])); nextID += 1
                responses.append(.array([]))
                responses.append(.integer(nextID)); nextID += 1
            }
        }
        let transport = FeatureTransport(responses)
        let result = try await featureClient(transport).security.createGroups()
        XCTAssertEqual(result.groupIDs.count, SECURITY_GROUP_DEFINITIONS.count)
        XCTAssertTrue(result.warnings.isEmpty)
        let calls = await transport.recorded()
        XCTAssertTrue(calls.contains { $0.model == "ir.model.access" && $0.method == "create" })
        XCTAssertTrue(calls.contains { $0.model == "ir.rule" && $0.method == "create" })
    }
}

final class TimerFeatureTests: XCTestCase {
    func testTimesheetParsingStateElapsedAndLabel() throws {
        let timesheet = try XCTUnwrap(parseTimesheet([
            "id": .integer(4), "name": .string("Work"),
            "project_id": .array([.integer(2), .string("Project")]),
            "task_id": .array([.integer(3), .string("Task")]),
            "unit_amount": .number(1.5), "timer_start": .bool(false),
            "date": .string("2026-01-02"),
        ]))
        XCTAssertEqual(timesheet.state, .stopped)
        XCTAssertEqual(timesheet.elapsedFormatted(), "1:30")
        XCTAssertEqual(timesheet.displayLabel, "🔧 Task")
    }

    func testRunningTimerElapsedIncludesLiveDuration() throws {
        let start = try OdooDateCodec.parseDateTime("2026-01-02 00:00:00")
        let end = try OdooDateCodec.parseDateTime("2026-01-02 01:15:00")
        let timesheet = Timesheet(
            id: 1, name: "", projectName: nil,
            source: TimerSource(kind: .standalone, id: 0, name: ""),
            unitAmount: 0.5, timerStart: start, date: start
        )
        XCTAssertEqual(timesheet.elapsedFormatted(now: end), "1:45")
        XCTAssertEqual(timesheet.displayLabel, "⏱ Timesheet")
    }

    func testMergeRunningTimersUpdatesExistingAndAppendsMissing() throws {
        let date = try OdooDateCodec.parseDate("2026-01-02")
        let start = try OdooDateCodec.parseDateTime("2026-01-02 03:00:00")
        let existing = Timesheet(
            id: 1, name: "Task", projectName: nil,
            source: TimerSource(kind: .task, id: 4, name: "Task"),
            unitAmount: 1, timerStart: nil, date: date
        )
        let running = buildRunningTimer(
            record: ["id": .integer(9)],
            source: TimerSource(kind: .task, id: 4, name: "Task"),
            projectName: nil, timerStart: start, today: date
        )
        let standalone = buildRunningTimer(
            record: ["id": .integer(10)],
            source: TimerSource(kind: .ticket, id: 5, name: "Ticket"),
            projectName: nil, timerStart: start, today: date
        )
        let merged = mergeRunningTimers([existing], [running, standalone])
        XCTAssertEqual(merged.count, 2)
        XCTAssertEqual(merged.first?.timerStart, start)
    }

    func testTimerListAndActiveOnJSON2() async throws {
        let record: OdooRecord = [
            "id": .integer(4), "name": .string("Work"), "unit_amount": .integer(0),
            "timer_start": .string("2026-01-02 03:04:05"), "date": .string("2026-01-02"),
        ]
        let transport = FeatureTransport([
            rows([]), rows([record]),
        ])
        let values = try await featureClient(transport).timer.active()
        XCTAssertEqual(values.map(\.id), [4])
        let calls = await transport.recorded()
        XCTAssertNil(calls[1].kwargs?["limit"])
        XCTAssertFalse(calls[1].args.description.contains("date"))
    }

    func testTimerStartsTaskAndTicket() async throws {
        let transport = FeatureTransport([.bool(true), .bool(true)])
        let timer = featureClient(transport).timer
        _ = try await timer.startTask(4)
        _ = try await timer.startTicket(5)
        let calls = await transport.recorded()
        XCTAssertEqual(calls.map(\.model), ["project.task", "helpdesk.ticket"])
        XCTAssertEqual(calls.map(\.method), ["action_timer_start", "action_timer_start"])
    }

    func testTimerStopsJSON2TimesheetAndCompletesWizard() async throws {
        let timesheet: OdooRecord = [
            "id": .integer(4), "name": .string("Work"), "unit_amount": .integer(0),
            "timer_start": .string("2026-01-02 03:04:05"), "date": .string("2026-01-02"),
        ]
        let action: OdooRecord = [
            "type": .string("ir.actions.act_window"),
            "res_model": .string("hr.timesheet.stop.timer.confirmation.wizard"),
            "context": .object(["default_timesheet_id": .integer(4)]),
        ]
        let transport = FeatureTransport([
            rows([]), rows([timesheet]), .object(action), .integer(9), .bool(true),
        ])
        try await featureClient(transport).timer.stopTimesheet(4)
        let calls = await transport.recorded()
        XCTAssertTrue(calls.contains { $0.model == "account.analytic.line" && $0.method == "action_timer_stop" })
        XCTAssertTrue(calls.contains { $0.model == "hr.timesheet.stop.timer.confirmation.wizard" && $0.method == "action_stop_timer" })
    }

    func testLegacyTimerListMergesTimerTimerRecords() async throws {
        let start = "2026-01-02 03:04:05"
        let transport = FeatureTransport([
            rows([]), rows([]),
            rows([["id": .integer(9), "timer_start": .string(start), "res_model": .string("project.task"), "res_id": .integer(4)]]),
            rows([["display_name": .string("Deploy"), "project_id": .array([.integer(2), .string("Project")])]]),
        ], dialect: .jsonrpc)
        let values = try await featureClient(transport).timer.list(days: -1)
        XCTAssertEqual(values.count, 1)
        XCTAssertEqual(values.first?.source, TimerSource(kind: .task, id: 4, name: "Deploy"))
        XCTAssertEqual(values.first?.projectName, "Project")
    }
}


final class AuthFeatureTests: XCTestCase {
    func testAuthResolvesConfiguredUserAndPartner() async throws {
        let transport = FeatureTransport([
            .array([.integer(7)]), rows([["partner_id": .array([.integer(8), .string("Ada")])]]),
        ])
        let client = featureClient(transport)
        let userID = try await getDefaultUserID(client: client)
        let partnerID = try await getPartnerIDFromUser(client: client, userID: userID)
        XCTAssertEqual(userID, 7)
        XCTAssertEqual(partnerID, 8)
        let calls = await transport.recorded()
        XCTAssertEqual(calls.first?.args.first, .array([
            .array([.string("login"), .string("="), .string("user")]),
        ]))
    }

    func testAuthReportsMissingUsersAndPartners() async {
        do {
            _ = try await getDefaultUserID(client: featureClient(FeatureTransport([.array([])])))
            XCTFail("Expected missing user")
        } catch let error as VodooError {
            XCTAssertEqual(error, .recordNotFound(model: "res.users", id: 0))
        } catch { XCTFail("Unexpected error: \(error)") }

        do {
            _ = try await getPartnerIDFromUser(
                client: featureClient(FeatureTransport([rows([["partner_id": .bool(false)]])])),
                userID: 7
            )
            XCTFail("Expected missing partner")
        } catch let error as VodooError {
            XCTAssertEqual(error, .recordNotFound(model: "res.partner", id: 0))
        } catch { XCTFail("Unexpected error: \(error)") }
    }

    func testAuthPostsCommentsAndNotesWithTypedPrecedence() async throws {
        let transport = FeatureTransport([
            rows([["partner_id": .integer(8)]]), rows([["res_id": .integer(4)]]), .integer(91),
            rows([["partner_id": .integer(8)]]), rows([["res_id": .integer(5)]]), .integer(92),
        ])
        let client = featureClient(transport, defaultUserID: 7)
        let commentID = try await messagePostSudoWithID(
            client: client, model: "project.task", recordID: 2, body: "<p>Done</p>",
            options: SudoMessageOptions(extraValues: [
                "model": .string("ignored"), "subject": .string("Status"),
            ])
        )
        let noted = try await messagePostSudo(
            client: client, model: "project.task", recordID: 2, body: "<p>Note</p>",
            options: SudoMessageOptions(isNote: true)
        )
        XCTAssertEqual(commentID, 91)
        XCTAssertTrue(noted)
        let calls = await transport.recorded()
        XCTAssertEqual(calls[2].args.first?.objectValue?["model"], .string("project.task"))
        XCTAssertEqual(calls[2].args.first?.objectValue?["subject"], .string("Status"))
        XCTAssertEqual(calls[5].args.first?.objectValue?["message_type"], .string("notification"))
    }

    func testAuthRequiresConfiguredMessageUser() async {
        do {
            _ = try await messagePostSudo(
                client: featureClient(FeatureTransport()),
                model: "project.task", recordID: 2, body: "x"
            )
            XCTFail("Expected configuration error")
        } catch let error as VodooError {
            XCTAssertEqual(error, .configuration("No default user ID configured"))
        } catch { XCTFail("Unexpected error: \(error)") }
    }
}
