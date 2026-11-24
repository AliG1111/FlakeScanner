import XCTest

final class CameraReportTests: XCTestCase {
    private func sampleReport() -> CameraReport {
        let depth = DepthFormatInfo(width_px: 768, height_px: 576, pixelFormat: "fdep", minFps: 2, maxFps: 30, isFiltered: false)
        let format = FormatInfo(width_px: 4032, height_px: 3024, pixelFormat: "420f", minFps: 1, maxFps: 60, isBinned: false,
                                supportsVideoHDR: true, fieldOfView_deg: 69.4, minISO: 25, maxISO: 6400,
                                minExposure_s: 1.0 / 33000.0, maxExposure_s: 1.0 / 3.0, maxZoomFactor: 15, depthFormats: [depth])
        let camera = CameraInfo(name: "Back Camera", deviceType: "builtInWideCamera", position: "back",
                                supportsDistortionCorrection: true, distortionCorrectionEnabled: true,
                                supportsLowLightBoost: false, minFocusDistance_mm: 120, supportsLockedLensPosition: true,
                                supportsCustomExposure: true, formats: [format], intrinsicsDeliverySupported: true,
                                activeFormatSummary: format.summary)
        return CameraReport(device: DeviceInfo(model: "iPhone", systemVersion: "iOS 26", appVersion: "Version 1.0 (build 9)",
                                               date: "2026-11-24"), cameras: [camera])
    }

    func testTextNamesTheCapabilities() {
        let text = sampleReport().text()
        XCTAssertTrue(text.contains("== Back Camera (builtInWideCamera, back)"))
        XCTAssertTrue(text.contains("4032×3024 420f 1–60 fps"))
        XCTAssertTrue(text.contains("ISO 25–6400"))
        XCTAssertTrue(text.contains("exposure 1/33000 s–1/3 s"))
        XCTAssertTrue(text.contains("video HDR"))
        XCTAssertTrue(text.contains("depth 768×576 fdep, up to 30 fps, filtered no"))
        XCTAssertTrue(text.contains("intrinsics delivery on 4032×3024 420f 1–60 fps: yes"))
        XCTAssertTrue(text.hasSuffix("\n"))
    }

    func testBinnedFormatIsMarked() {
        var report = sampleReport()
        report.cameras[0].formats[0].isBinned = true
        XCTAssertTrue(report.text().contains("binned"))
    }

    func testJSONRoundTrip() throws {
        let report = sampleReport()
        let data = try JSONFile.encode(report)
        let back = try JSONFile.decode(CameraReport.self, from: data)
        XCTAssertEqual(back, report)
        let json = String(decoding: data, as: UTF8.self)
        XCTAssertTrue(json.contains("\"cameras\""))
    }

    func testJSONDecodesAFileWithoutLaterFields() throws {
        // A file written by an older build has no `maxZoomFactor` and no depth formats key set: Optional fields only.
        let old = """
        {"width_px":1920,"height_px":1080,"pixelFormat":"420f","minFps":1,"maxFps":30,"isBinned":false,
         "supportsVideoHDR":false,"fieldOfView_deg":60,"minISO":50,"maxISO":1600,"minExposure_s":0.0001,
         "maxExposure_s":0.3,"depthFormats":[]}
        """
        let format = try JSONFile.decode(FormatInfo.self, from: Data(old.utf8))
        XCTAssertNil(format.maxZoomFactor)
        XCTAssertEqual(format.width_px, 1920)
    }

    func testExposureText() {
        XCTAssertEqual(CameraReport.exposureText(1.0 / 2800.0), "1/2800 s")
        XCTAssertEqual(CameraReport.exposureText(0.5), "0.50 s")
        XCTAssertEqual(CameraReport.exposureText(0), "?")
        XCTAssertEqual(CameraReport.exposureText(.nan), "?")
    }

    func testLidarReportText() {
        let reading = DistanceReading(distance_mm: 1203, spread_mm: 4.2, mapCount: 30, goodMapCount: 30,
                                      validShare: 0.97, isValid: true, problem: nil)
        let bad = DistanceReading(distance_mm: nil, spread_mm: nil, mapCount: 30, goodMapCount: 0, validShare: 0,
                                  isValid: false, problem: "No valid depth in the region")
        let state = LidarReport.CameraState(exposure_s: 1.0 / 2800.0, iso: 1600, lensPosition: 0.8, whiteBalanceGains: [1.8, 1, 1.5])
        let report = LidarReport(
            formatChecks: [LidarReport.FormatCheck(format: "1920×1440 420f", depthFormat: "768×576 fdep",
                                                   acceptsCustomExposure: true, acceptsLockedFocus: true,
                                                   acceptsFixedFrameDuration: true, framesDelivered: 28,
                                                   deliveredFps: 29.5, note: nil)],
            timeToFirstDepth_s: 0.62, settleOnLidar_s: 0.9, timeBackToFirstFrame_s: 0.41,
            stateBefore: state, stateAfterSwitch: state, stateAfterLock: state,
            zones: [LidarReport.Zone(name: "ROI", reading: reading), LidarReport.Zone(name: "corner", reading: bad)],
            depthMapSize: "768×576", tapeMeasure_mm: 1200, notes: ["note"])
        let text = report.text()
        XCTAssertTrue(text.contains("custom exposure yes, locked focus yes, fixed frame duration yes; 28 frames at 29.5 fps"))
        XCTAssertTrue(text.contains("time to first depth: 0.62 s"))
        XCTAssertTrue(text.contains("ROI: 1203 mm, spread 4.2 mm, valid 97 %"))
        XCTAssertTrue(text.contains("corner: no reading (No valid depth in the region)"))
        XCTAssertTrue(text.contains("exposure 1/2800 s, ISO 1600, lens 0.800, white balance gains 1.800 / 1.000 / 1.500"))
        XCTAssertTrue(text.contains("tape measure: 1200 mm"))
        XCTAssertNoThrow(try JSONFile.encode(report))
    }
}
