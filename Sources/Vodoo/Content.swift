import Foundation

/// Rich text accepted by helpers that write Odoo HTML fields.
public enum RichText: Sendable, Equatable, ExpressibleByStringLiteral {
    case markdown(String)
    case html(String)
    case plain(String)

    public init(stringLiteral value: String) { self = .markdown(value) }
}

public enum OdooContent {
    public static func markdownToHTML(_ value: String) -> String {
        let normalized = value.replacingOccurrences(of: "\r\n", with: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if normalized.isEmpty { return "" }
        return normalized.components(separatedBy: try! NSRegularExpression(pattern: "\\n{2,}") )
            .map(renderBlock)
            .joined(separator: "\n")
    }

    public static func richTextToHTML(_ value: RichText, markdownByDefault: Bool = true) -> String {
        switch value {
        case let .html(text): return text
        case let .markdown(text): return markdownToHTML(text)
        case let .plain(text):
            return markdownByDefault ? markdownToHTML(text) : "<p>\(escapeHTML(text))</p>"
        }
    }

    private static func renderBlock(_ block: String) -> String {
        if let match = block.firstMatch(#"^(#{1,6})\s+(.+)$"#),
           let hashes = match[safe: 1], let body = match[safe: 2] {
            return "<h\(hashes.count)>\(renderInline(body))</h\(hashes.count)>"
        }
        let lines = block.components(separatedBy: "\n")
        if lines.allSatisfy({ $0.range(of: #"^\s*[-*+]\s+"#, options: .regularExpression) != nil }) {
            let items = lines.map { line in
                let value = line.replacingOccurrences(
                    of: #"^\s*[-*+]\s+"#,
                    with: "",
                    options: .regularExpression
                )
                return "<li>\(renderInline(value))</li>"
            }.joined(separator: "\n")
            return "<ul>\n\(items)\n</ul>"
        }
        return "<p>\(lines.map(renderInline).joined(separator: "<br />\n"))</p>"
    }

    private static func renderInline(_ value: String) -> String {
        var result = escapeHTML(value)
        result = result.replacingMatches(#"`([^`]+)`"#, with: "<code>$1</code>")
        result = result.replacingMatches(#"\*\*([^*]+)\*\*"#, with: "<strong>$1</strong>")
        result = result.replacingMatches(#"__([^_]+)__"#, with: "<strong>$1</strong>")

        let linkPattern = try! NSRegularExpression(pattern: #"\[(.+?)\]\(([^)]+)\)"#)
        let source = result
        let matches = linkPattern.matches(in: source, range: NSRange(source.startIndex..., in: source))
        for match in matches.reversed() {
            guard let full = Range(match.range(at: 0), in: result),
                  let labelRange = Range(match.range(at: 1), in: source),
                  let hrefRange = Range(match.range(at: 2), in: source) else { continue }
            let label = String(source[labelRange])
            let href = String(source[hrefRange])
            if safeLink(href) { result.replaceSubrange(full, with: "<a href=\"\(href)\">\(label)</a>") }
        }
        result = result.replacingMatches(#"(?<!\*)\*([^*]+)\*(?!\*)"#, with: "<em>$1</em>")
        return result
    }

    private static func safeLink(_ href: String) -> Bool {
        let value = href.trimmingCharacters(in: .whitespacesAndNewlines)
        let compact = value.unicodeScalars.filter { $0.value > 32 }.map(String.init).joined()
        if compact.range(of: #"^(?:https?:|mailto:|tel:|/|#|\.\.?/)"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return true
        }
        return !compact.contains(":")
    }

    private static func escapeHTML(_ value: String) -> String {
        value.replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
            .replacingOccurrences(of: ">", with: "&gt;")
            .replacingOccurrences(of: "\"", with: "&quot;")
            .replacingOccurrences(of: "'", with: "&#39;")
    }
}

private extension String {
    func replacingMatches(_ pattern: String, with template: String) -> String {
        let expression = try! NSRegularExpression(pattern: pattern)
        return expression.stringByReplacingMatches(
            in: self,
            range: NSRange(startIndex..., in: self),
            withTemplate: template
        )
    }

    func firstMatch(_ pattern: String) -> [String?]? {
        let expression = try! NSRegularExpression(pattern: pattern)
        guard let match = expression.firstMatch(in: self, range: NSRange(startIndex..., in: self)) else {
            return nil
        }
        return (0 ..< match.numberOfRanges).map { index in
            guard let range = Range(match.range(at: index), in: self) else { return nil }
            return String(self[range])
        }
    }
}

private extension Array where Element == String? {
    subscript(safe index: Int) -> String? {
        indices.contains(index) ? self[index] : nil
    }
}

private extension String {
    func components(separatedBy expression: NSRegularExpression) -> [String] {
        let range = NSRange(startIndex..., in: self)
        var result: [String] = []
        var cursor = startIndex
        for match in expression.matches(in: self, range: range) {
            guard let separator = Range(match.range, in: self) else { continue }
            result.append(String(self[cursor ..< separator.lowerBound]))
            cursor = separator.upperBound
        }
        result.append(String(self[cursor...]))
        return result
    }
}
