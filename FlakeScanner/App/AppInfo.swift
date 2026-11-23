import Foundation

/// Pure helpers for the About screen. They take the bundle's info dictionary as a parameter so tests can
/// pass their own values (the test bundle compiles this file directly).
enum AppInfo {
    /// The text shown under the app name, for example "Version 1.0 (build 7)".
    ///
    /// Fallbacks when a key is missing or blank:
    /// - version only: "Version 1.0"
    /// - build only: "Build 7"
    /// - neither: "Version unknown"
    static func versionText(_ info: [String: Any]) -> String {
        let version = value(info["CFBundleShortVersionString"])
        let build = value(info["CFBundleVersion"])
        switch (version, build) {
        case let (version?, build?):
            return "Version \(version) (build \(build))"
        case let (version?, nil):
            return "Version \(version)"
        case let (nil, build?):
            return "Build \(build)"
        case (nil, nil):
            return "Version unknown"
        }
    }

    /// A trimmed, non-empty string for a plist value, or nil. Whole numbers are accepted too, because a
    /// build number written as a plist integer is still a build number.
    private static func value(_ raw: Any?) -> String? {
        let text: String
        if let string = raw as? String {
            text = string
        } else if let number = raw as? Int {
            text = String(number)
        } else {
            return nil
        }
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
