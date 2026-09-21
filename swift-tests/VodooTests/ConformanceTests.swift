import Foundation
import XCTest
@testable import Vodoo

private func fixture() throws -> [String: Any] {
    let url = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        .appendingPathComponent("conformance/fixtures/v1.json")
    return try XCTUnwrap(
        JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
    )
}

private func jsonValue(_ value: Any) throws -> JSONValue {
    let data = try JSONSerialization.data(withJSONObject: value, options: [.fragmentsAllowed])
    return try JSONDecoder().decode(JSONValue.self, from: data)
}

private struct RecordedCall: Sendable, Equatable {
    let model: String
    let method: String
    let args: [JSONValue]
    let kwargs: OdooRecord?
}

private actor QueueTransport: OdooTransportProtocol {
    nonisolated let dialect = TransportDialect.json2
    var responses: [JSONValue]
    var calls: [RecordedCall] = []
    init(_ responses: [JSONValue]) { self.responses = responses }
    func getUID() async throws -> Int { 7 }
    func execute(
        model: String,
        method: String,
        args: [JSONValue],
        kwargs: OdooRecord?
    ) async throws -> JSONValue {
        calls.append(RecordedCall(model: model, method: method, args: args, kwargs: kwargs))
        guard !responses.isEmpty else { throw VodooError.invalidResponse("No response") }
        return responses.removeFirst()
    }
    func recordedCalls() -> [RecordedCall] { calls }
}

final class ConformanceTests: XCTestCase {
    func testBinaryCodecFollowsSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["binary"] as? [[String: Any]])
        for row in rows {
            let bytes = try XCTUnwrap(row["bytes"] as? [Int])
            let data = Data(bytes.map(UInt8.init))
            let base64 = try XCTUnwrap(row["base64"] as? String)
            XCTAssertEqual(OdooBinaryCodec.encode(data), base64)
            XCTAssertEqual(try OdooBinaryCodec.decode(base64), data)
        }
    }

    func testCommandsFollowSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["commands"] as? [[String: Any]])
        for row in rows {
            let operation = try XCTUnwrap(row["operation"] as? String)
            let args = try XCTUnwrap(row["args"] as? [Any])
            let actual: JSONValue
            switch operation {
            case "create": actual = Command.create(try XCTUnwrap(jsonValue(args[0]).objectValue)).wireValue
            case "update": actual = Command.update(
                try XCTUnwrap(jsonValue(args[0]).intValue),
                try XCTUnwrap(jsonValue(args[1]).objectValue)
            ).wireValue
            case "delete": actual = Command.delete(try XCTUnwrap(jsonValue(args[0]).intValue)).wireValue
            case "unlink": actual = Command.unlink(try XCTUnwrap(jsonValue(args[0]).intValue)).wireValue
            case "link": actual = Command.link(try XCTUnwrap(jsonValue(args[0]).intValue)).wireValue
            case "clear": actual = Command.clear.wireValue
            case "set":
                guard case let .array(ids) = try jsonValue(args[0]) else {
                    throw VodooError.invalidResponse("ids")
                }
                actual = Command.set(try ids.map { try XCTUnwrap($0.intValue) }).wireValue
            default: throw VodooError.invalidResponse(operation)
            }
            XCTAssertEqual(actual, try jsonValue(try XCTUnwrap(row["expect"])))
        }
    }

    func testJSON2ResponsesFollowSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["json2Responses"] as? [[String: Any]])
        for row in rows {
            let wire = try XCTUnwrap(row["wire"] as? String)
            XCTAssertEqual(
                try parseJSON2Response(wire),
                try jsonValue(try XCTUnwrap(row["expect"]))
            )
        }
    }

    func testJSON2BodiesFollowSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["json2Bodies"] as? [[String: Any]])
        for row in rows {
            let method = try XCTUnwrap(row["method"] as? String)
            let args = try XCTUnwrap(row["args"] as? [Any]).map(jsonValue)
            let kwargs = try (row["kwargs"] as? [String: Any])?.mapValues(jsonValue)
            if row["expectError"] != nil {
                XCTAssertThrowsError(try buildJSON2Body(method: method, args: args, kwargs: kwargs))
            } else {
                XCTAssertEqual(
                    try buildJSON2Body(method: method, args: args, kwargs: kwargs),
                    try XCTUnwrap(jsonValue(try XCTUnwrap(row["expect"])).objectValue)
                )
            }
        }
    }

    func testErrorsFollowSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["errors"] as? [[String: Any]])
        for row in rows {
            let error = makeOdooError(
                message: try XCTUnwrap(row["message"] as? String),
                code: try XCTUnwrap(row["code"] as? Int),
                data: try XCTUnwrap(jsonValue(try XCTUnwrap(row["data"])).objectValue)
            )
            switch try XCTUnwrap(row["class"] as? String) {
            case "OdooAccessError":
                guard case .access = error else { return XCTFail("Expected access error") }
            case "OdooValidationError":
                guard case .validation = error else { return XCTFail("Expected validation error") }
            default:
                guard case .transport = error else { return XCTFail("Expected transport error") }
            }
            XCTAssertEqual(error.description, try XCTUnwrap(row["rendered"] as? String))
        }
    }

    func testDatesFollowSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["dates"] as? [[String: Any]])
        for row in rows {
            let wire = try XCTUnwrap(row["wire"] as? String)
            let kind = try XCTUnwrap(row["kind"] as? String)
            if row["expectError"] != nil {
                XCTAssertThrowsError(
                    try kind == "date"
                        ? OdooDateCodec.parseDate(wire)
                        : OdooDateCodec.parseDateTime(wire)
                )
            } else {
                let value = try kind == "date"
                    ? OdooDateCodec.parseDate(wire)
                    : OdooDateCodec.parseDateTime(wire)
                let encoded = try kind == "date"
                    ? OdooDateCodec.formatDate(value)
                    : OdooDateCodec.formatDateTime(value)
                XCTAssertEqual(encoded, wire)
            }
        }
    }

    func testRetryPolicyFollowsSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["retry"] as? [[String: Any]])
        let policy = RetryPolicy()
        for row in rows {
            let method = try XCTUnwrap(row["method"] as? String)
            let attempt = try XCTUnwrap(row["attempt"] as? Int)
            let retryable = try XCTUnwrap(row["retryable"] as? Bool)
            let delayMilliseconds = try XCTUnwrap(row["delayMs"] as? Int)
            XCTAssertEqual(policy.isRetryable(method: method), retryable)
            XCTAssertEqual(policy.delay(attempt: attempt) * 1_000, Double(delayMilliseconds))
        }
    }

    func testLegacyAuthenticationEnvelopeFollowsSharedFixture() throws {
        let rows = try XCTUnwrap(fixture()["transports"] as? [[String: Any]])
        let row = try XCTUnwrap(rows.first { ($0["dialect"] as? String) == "jsonrpc" })
        let config = try XCTUnwrap(row["config"] as? [String: Any])
        let expected = try XCTUnwrap(row["expect"] as? [String: Any])
        let requests = try XCTUnwrap(expected["requests"] as? [[String: Any]])
        let expectedPayload = try jsonValue(try XCTUnwrap(requests.first?["json"]))
        let payload = buildLegacyPayload(
            service: "common",
            method: "authenticate",
            args: [
                .string(try XCTUnwrap(config["database"] as? String)),
                .string(try XCTUnwrap(config["username"] as? String)),
                .string(try XCTUnwrap(config["password"] as? String)),
                .object([:]),
            ]
        )
        XCTAssertEqual(payload, expectedPayload)
    }

    func testNameSearchNormalizationFollowsSharedFixture() async throws {
        let contract = try XCTUnwrap(fixture()["nameSearch"] as? [String: Any])
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test")),
                database: "fixture",
                username: "user",
                password: "key"
            ),
            transport: QueueTransport([try jsonValue(try XCTUnwrap(contract["input"]))])
        )
        let expectedRows = try XCTUnwrap(contract["expect"] as? [[Any]])
        let expected = try expectedRows.map {
            NameSearchResult(
                id: try XCTUnwrap(jsonValue($0[0]).intValue),
                name: try XCTUnwrap(jsonValue($0[1]).stringValue)
            )
        }
        let actual = try await client.nameSearch(model: "res.partner", name: "a")
        XCTAssertEqual(actual, expected)
    }

    func testCreateResultsFollowSharedFixture() async throws {
        let rows = try XCTUnwrap(fixture()["createResults"] as? [[String: Any]])
        for row in rows {
            let client = OdooClient(
                config: OdooConfig(
                    url: try XCTUnwrap(URL(string: "https://odoo.example.test")),
                    database: "fixture",
                    username: "user",
                    password: "key"
                ),
                transport: QueueTransport([try jsonValue(try XCTUnwrap(row["wire"]))])
            )
            if row["expectError"] != nil {
                do {
                    _ = try await client.create(model: "res.partner", values: [:])
                    XCTFail("Expected invalid create result")
                } catch {}
            } else {
                let actual = try await client.create(model: "res.partner", values: [:])
                XCTAssertEqual(actual, try XCTUnwrap(row["expect"] as? Int))
            }
        }
    }

    func testGenericAndDomainCRUDUseThePortableClientContract() async throws {
        let transport = QueueTransport([
            .array([.integer(4), .integer(5)]),
            .array([.object(["id": .integer(4), "name": .string("Ada")])]),
            .array([.object(["id": .integer(5), "name": .string("Grace")])]),
            .integer(6),
            .bool(true),
            .bool(true),
            .object(["name": .object(["type": .string("char")])]),
            .array([.array([.integer(4), .string("Ada")])]),
            .array([.object(["id": .integer(7), "name": .string("Project")])]),
            .array([.object(["id": .integer(7), "name": .string("Project")])]),
            .bool(true),
            .object(["name": .object(["type": .string("char")])]),
        ])
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test/")),
                database: "fixture",
                username: "user",
                password: "key"
            ),
            transport: transport
        )
        let generic = client.generic("res.partner")
        let ids = try await generic.search(limit: 2)
        let read = try await generic.read([4])
        let searchRead = try await generic.searchRead(limit: 1)
        let createdID = try await generic.create(["name": .string("Lin")])
        let didWrite = try await generic.write([6], values: ["name": .string("Linus")])
        let didUnlink = try await generic.unlink([6])
        let fields = try await generic.fields()
        let names = try await generic.nameSearch("Ada")
        XCTAssertEqual(ids, [4, 5])
        XCTAssertEqual(read.first?["name"], .string("Ada"))
        XCTAssertEqual(searchRead.first?["name"], .string("Grace"))
        XCTAssertEqual(createdID, 6)
        XCTAssertTrue(didWrite)
        XCTAssertTrue(didUnlink)
        XCTAssertNotNil(fields["name"])
        XCTAssertEqual(names, [NameSearchResult(id: 4, name: "Ada")])

        let projects = try await client.projects.list(limit: 1)
        let project = try await client.projects.get(7)
        let didSet = try await client.projects.set(7, values: ["name": .string("Updated")])
        let projectFields = try await client.projects.fields()
        XCTAssertEqual(projects.first?["id"], .integer(7))
        XCTAssertEqual(project["name"], .string("Project"))
        XCTAssertTrue(didSet)
        XCTAssertNotNil(projectFields["name"])
        XCTAssertEqual(
            client.projects.url(7).absoluteString,
            "https://odoo.example.test/web#id=7&model=project.project&view_type=form"
        )
    }

    func testHelpdeskCreateFollowsSharedOperationFixture() async throws {
        let rows = try XCTUnwrap(fixture()["operations"] as? [[String: Any]])
        let row = try XCTUnwrap(rows.first { ($0["id"] as? String) == "helpdesk-create" })
        let input = try XCTUnwrap(row["input"] as? [String: Any])
        let expectedValues = try XCTUnwrap(row["expectedValues"] as? [String: Any])
        let transport = QueueTransport([
            try jsonValue(try XCTUnwrap(row["expectedResult"]))
        ])
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test")),
                database: "fixture",
                username: "user",
                password: "key"
            ),
            transport: transport
        )
        let extraFields = try XCTUnwrap(input["extraFields"] as? [String: Any])
        let id = try await client.helpdesk.create(
            try XCTUnwrap(input["name"] as? String),
            options: CreateTicketOptions(
                description: input["description"] as? String,
                partnerID: input["partnerId"] as? Int,
                tagIDs: input["tagIds"] as? [Int],
                teamID: input["teamId"] as? Int,
                extraFields: try extraFields.mapValues(jsonValue)
            )
        )
        XCTAssertEqual(id, try XCTUnwrap(row["expectedResult"] as? Int))
        let calls = await transport.recordedCalls()
        XCTAssertEqual(
            calls,
            [
                RecordedCall(
                    model: try XCTUnwrap(row["expectedModel"] as? String),
                    method: "create",
                    args: [.object(try expectedValues.mapValues(jsonValue))],
                    kwargs: nil
                )
            ]
        )
    }

    func testGeneratedNamespaceMetadataIsAvailable() throws {
        let client = OdooClient(
            config: OdooConfig(
                url: try XCTUnwrap(URL(string: "https://odoo.example.test")),
                database: "fixture",
                username: "user",
                password: "key"
            ),
            transport: QueueTransport([])
        )
        XCTAssertEqual(client.projects.model, "project.project")
        XCTAssertEqual(client.helpdesk.availability.editions, ["enterprise"])
        XCTAssertTrue(client.tasks.capabilities.contains("tags"))
    }
}
