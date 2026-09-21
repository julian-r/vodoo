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

        let partners = client.generic("res.partner")
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
}
