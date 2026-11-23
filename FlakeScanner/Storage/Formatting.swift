import Foundation

enum Units {
    /// "12.4 MB"
    static func bytes(_ count: Int64) -> String {
        ByteCountFormatter.string(fromByteCount: count, countStyle: .file)
    }
}

/// Locale-independent number text for files and exports: always a "." decimal separator and no grouping.
enum Num {
    /// `value` with exactly `decimals` digits after the point ("12.50"), or "" when it is NaN or infinite.
    /// Negative zero and values that round to zero print without a sign ("0.00", never "-0.00").
    /// Rounding is that of C `printf` (`String(format:)`): the exact binary value is rounded to the nearest digit and
    /// an exact tie goes to the even digit, so 0.125 with 2 decimals is "0.12" and 2.5 with 0 decimals is "2". This
    /// matches Python's `%` formatting, which the lab uses.
    static func fixed(_ value: Double, _ decimals: Int) -> String {
        guard value.isFinite else { return "" }
        let places = max(0, decimals)
        let text = String(format: "%.\(places)f", value)
        // "-0.00" (from -0.0 or a tiny negative value) is the same number as "0.00".
        if text.hasPrefix("-"), !text.contains(where: { $0 != "-" && $0 != "0" && $0 != "." }) {
            return String(text.dropFirst())
        }
        return text
    }
}

enum CSV {
    /// Quotes a field that contains a comma, a double quote, CR or LF (RFC 4180) and doubles its quotes. The check is
    /// on unicode scalars: a CR-LF pair is a single `Character`, so a `Character` test would miss it.
    static func escape(_ field: String) -> String {
        guard field.unicodeScalars.contains(where: { $0 == "," || $0 == "\"" || $0 == "\n" || $0 == "\r" }) else {
            return field
        }
        return "\"" + field.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }

    static func make(_ rows: [[String]]) -> String {
        rows.map { $0.map(escape).joined(separator: ",") }.joined(separator: "\n") + "\n"
    }
}
