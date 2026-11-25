import Foundation

/// Where the probe's files go: `Documents/Diagnostics/<time>-<kind>/` (visible in the Files app), and the zip of all
/// of them (design §3.8, FR-APP-06 e). Files stay on the phone until shared, and are never committed.
enum DiagnosticsStore {
    static let folderName = "Diagnostics"

    static var root: URL {
        let documents = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first
            ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
        return documents.appendingPathComponent(folderName, isDirectory: true)
    }

    static func stamp(_ date: Date = Date()) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        return formatter.string(from: date)
    }

    /// A new folder `<time>-<kind>` (kind is a short file-name-safe word).
    static func newFolder(kind: String) throws -> URL {
        let safe = kind.filter { $0.isLetter || $0.isNumber || $0 == "-" }
        let folder = root.appendingPathComponent("\(stamp())-\(safe)", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        return folder
    }

    static func write(_ text: String, name: String, in folder: URL) throws {
        try Data(text.utf8).write(to: folder.appendingPathComponent(name), options: .atomic)
    }

    static func write(_ data: Data, name: String, in folder: URL) throws {
        try data.write(to: folder.appendingPathComponent(name), options: .atomic)
    }

    /// Number of files and their total size under the diagnostics folder.
    static func summary() -> (files: Int, bytes: Int64) {
        guard let walker = FileManager.default.enumerator(at: root, includingPropertiesForKeys: [.fileSizeKey, .isRegularFileKey]) else {
            return (0, 0)
        }
        var files = 0
        var bytes: Int64 = 0
        for case let url as URL in walker {
            let values = try? url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
            if values?.isRegularFile == true {
                files += 1
                bytes += Int64(values?.fileSize ?? 0)
            }
        }
        return (files, bytes)
    }

    /// Zips the whole diagnostics folder into the temporary directory and returns the zip's URL.
    static func makeZip() throws -> URL {
        let fileManager = FileManager.default
        try fileManager.createDirectory(at: root, withIntermediateDirectories: true)
        var coordinationError: NSError?
        var outcome: Result<URL, Error>?
        NSFileCoordinator().coordinate(readingItemAt: root, options: [.forUploading], error: &coordinationError) { zipped in
            do {
                let destination = fileManager.temporaryDirectory.appendingPathComponent("FlakeScanner-diagnostics-\(stamp()).zip")
                try? fileManager.removeItem(at: destination)
                try fileManager.copyItem(at: zipped, to: destination)
                outcome = .success(destination)
            } catch {
                outcome = .failure(error)
            }
        }
        if let coordinationError { throw coordinationError }
        guard let outcome else { throw CaptureError.configuration("The zip file could not be made.") }
        return try outcome.get()
    }

    /// Removes every probe result (after the zip has been shared).
    static func deleteAll() throws {
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: root.path) else { return }
        try fileManager.removeItem(at: root)
    }
}
