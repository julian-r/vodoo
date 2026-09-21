import Foundation

public struct RetryPolicy: Sendable, Equatable {
    public let maxRetries: Int
    public let backoffBase: TimeInterval
    public let backoffMaximum: TimeInterval

    public init(
        maxRetries: Int = 2,
        backoffBase: TimeInterval = 0.5,
        backoffMaximum: TimeInterval = 30
    ) {
        self.maxRetries = maxRetries
        self.backoffBase = backoffBase
        self.backoffMaximum = backoffMaximum
    }

    public func delay(attempt: Int) -> TimeInterval {
        min(backoffBase * pow(2, Double(attempt)), backoffMaximum)
    }

    public func isRetryable(method: String) -> Bool {
        ["search", "search_read", "read", "fields_get", "name_search"].contains(method)
    }
}
