import Foundation

/// The one JSON encoder and decoder for files the app writes (readable by people, stable key order, so a file
/// diffs cleanly and a later build can still read it). New `Codable` fields stay Optional.
enum JSONFile {
    static func encode<T: Encodable>(_ value: T) throws -> Data {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return try encoder.encode(value)
    }

    static func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        try JSONDecoder().decode(type, from: data)
    }
}
