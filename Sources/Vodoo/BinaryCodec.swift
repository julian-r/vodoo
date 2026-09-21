import Foundation

public enum OdooBinaryCodec {
    public static func encode(_ data: Data) -> String {
        data.base64EncodedString()
    }

    public static func decode(_ value: String) throws -> Data {
        guard let data = Data(base64Encoded: value) else {
            throw VodooError.invalidResponse("Invalid base64 data")
        }
        return data
    }
}
