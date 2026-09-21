import Foundation

public enum OdooDateKind: String, Sendable, Equatable {
    case date
    case dateTime = "datetime"
}

public func decodeRecordDates(
    _ record: OdooRecord,
    fields: [String: OdooDateKind]
) throws -> OdooRecord {
    var result = record
    for (field, kind) in fields {
        guard case let .string(value) = result[field] else { continue }
        switch kind {
        case .date:
            result[field] = .date(try OdooDateCodec.parseDate(value))
        case .dateTime:
            result[field] = .dateTime(try OdooDateCodec.parseDateTime(value))
        }
    }
    return result
}

public enum OdooDateCodec {
    private static let utc = TimeZone(secondsFromGMT: 0)!
    private static var calendar: Calendar {
        var value = Calendar(identifier: .gregorian)
        value.timeZone = utc
        return value
    }

    public static func parseDate(_ value: String) throws -> Date {
        try parse(value, includeTime: false)
    }

    public static func parseDateTime(_ value: String) throws -> Date {
        try parse(value, includeTime: true)
    }

    private static func parse(_ value: String, includeTime: Bool) throws -> Date {
        let pattern = includeTime
            ? #"^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})$"#
            : #"^(\d{4})-(\d{2})-(\d{2})$"#
        guard let expression = try? NSRegularExpression(pattern: pattern),
              let match = expression.firstMatch(
                in: value,
                range: NSRange(value.startIndex..., in: value)
              ) else {
            throw VodooError.invalidResponse("Invalid Odoo date: \(value)")
        }
        func part(_ index: Int) -> Int? {
            guard let range = Range(match.range(at: index), in: value) else { return nil }
            return Int(value[range])
        }
        guard let year = part(1), year > 0, let month = part(2), let day = part(3) else {
            throw VodooError.invalidResponse("Invalid Odoo date: \(value)")
        }
        let hour = includeTime ? part(4) ?? -1 : 0
        let minute = includeTime ? part(5) ?? -1 : 0
        let second = includeTime ? part(6) ?? -1 : 0
        let components = DateComponents(
            timeZone: utc,
            year: year,
            month: month,
            day: day,
            hour: hour,
            minute: minute,
            second: second
        )
        guard let date = calendar.date(from: components) else {
            throw VodooError.invalidResponse("Invalid Odoo date: \(value)")
        }
        let roundTrip = calendar.dateComponents(
            [.year, .month, .day, .hour, .minute, .second],
            from: date
        )
        guard roundTrip.year == year, roundTrip.month == month, roundTrip.day == day,
              roundTrip.hour == hour, roundTrip.minute == minute, roundTrip.second == second else {
            throw VodooError.invalidResponse("Invalid Odoo date: \(value)")
        }
        return date
    }

    public static func formatDate(_ value: Date) throws -> String {
        let parts = calendar.dateComponents([.year, .month, .day], from: value)
        guard let year = parts.year, (1 ... 9999).contains(year),
              let month = parts.month, let day = parts.day else {
            throw VodooError.invalidResponse("Date is outside Odoo's supported range")
        }
        return String(format: "%04d-%02d-%02d", year, month, day)
    }

    public static func formatDateTime(_ value: Date) throws -> String {
        let date = try formatDate(value)
        let parts = calendar.dateComponents([.hour, .minute, .second], from: value)
        return String(
            format: "%@ %02d:%02d:%02d",
            date,
            parts.hour ?? 0,
            parts.minute ?? 0,
            parts.second ?? 0
        )
    }
}
