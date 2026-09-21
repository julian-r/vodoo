// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Vodoo",
    platforms: [.macOS(.v13), .iOS(.v16)],
    products: [.library(name: "Vodoo", targets: ["Vodoo"])],
    targets: [
        .target(name: "Vodoo"),
        .testTarget(
            name: "VodooTests",
            dependencies: ["Vodoo"],
            path: "swift-tests/VodooTests"
        ),
    ]
)
