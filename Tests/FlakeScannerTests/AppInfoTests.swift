import XCTest

final class AppInfoTests: XCTestCase {
    func testVersionAndBuild() {
        let info: [String: Any] = ["CFBundleShortVersionString": "1.0", "CFBundleVersion": "7"]
        XCTAssertEqual(AppInfo.versionText(info), "Version 1.0 (build 7)")
    }

    func testBuildGivenAsAnInteger() {
        let info: [String: Any] = ["CFBundleShortVersionString": "1.2", "CFBundleVersion": 42]
        XCTAssertEqual(AppInfo.versionText(info), "Version 1.2 (build 42)")
    }

    func testMissingBuildShowsOnlyTheVersion() {
        let info: [String: Any] = ["CFBundleShortVersionString": "1.0"]
        XCTAssertEqual(AppInfo.versionText(info), "Version 1.0")
    }

    func testMissingVersionShowsOnlyTheBuild() {
        let info: [String: Any] = ["CFBundleVersion": "7"]
        XCTAssertEqual(AppInfo.versionText(info), "Build 7")
    }

    func testEmptyDictionaryIsUnknown() {
        XCTAssertEqual(AppInfo.versionText([:]), "Version unknown")
    }

    func testBlankAndWrongTypeValuesCountAsMissing() {
        let blank: [String: Any] = ["CFBundleShortVersionString": "  ", "CFBundleVersion": ""]
        XCTAssertEqual(AppInfo.versionText(blank), "Version unknown")
        let wrongType: [String: Any] = ["CFBundleShortVersionString": ["1.0"], "CFBundleVersion": [1, 2]]
        XCTAssertEqual(AppInfo.versionText(wrongType), "Version unknown")
    }

    func testValuesAreTrimmed() {
        let info: [String: Any] = ["CFBundleShortVersionString": " 1.0\n", "CFBundleVersion": " 7 "]
        XCTAssertEqual(AppInfo.versionText(info), "Version 1.0 (build 7)")
    }
}
