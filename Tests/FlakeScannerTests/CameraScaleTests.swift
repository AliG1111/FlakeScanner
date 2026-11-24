import XCTest

final class NormalizedRectTests: XCTestCase {
    func testPixelBoundsRoundToWholePixelsInsideTheFrame() {
        let rect = NormalizedRect(x: 0.25, y: 0.1, width: 0.5, height: 0.8)
        let box = rect.pixelBounds(width_px: 4000, height_px: 3000)
        XCTAssertEqual(box?.x0, 1000)
        XCTAssertEqual(box?.x1, 3000)
        XCTAssertEqual(box?.y0, 300)
        XCTAssertEqual(box?.y1, 2700)
    }

    func testPixelBoundsClampToTheFrameAndKeepOnePixel() {
        let box = NormalizedRect(x: -0.5, y: 0.9, width: 3, height: 0.5).pixelBounds(width_px: 100, height_px: 50)
        XCTAssertEqual(box?.x0, 0)
        XCTAssertEqual(box?.x1, 100)
        XCTAssertEqual(box?.y0, 45)
        XCTAssertEqual(box?.y1, 50)
        let sliver = NormalizedRect(x: 0.999, y: 0.5, width: 0.0001, height: 0.1).pixelBounds(width_px: 100, height_px: 100)
        XCTAssertEqual((sliver?.x1 ?? 0) - (sliver?.x0 ?? 0), 1)
    }

    func testPixelBoundsOfAnEmptyRectangleOrFrame() {
        XCTAssertNil(NormalizedRect(x: 0.2, y: 0.2, width: 0, height: 0.5).pixelBounds(width_px: 100, height_px: 100))
        XCTAssertNil(NormalizedRect.full.pixelBounds(width_px: 0, height_px: 100))
        XCTAssertNil(NormalizedRect(x: 1.5, y: 0, width: 0.5, height: 1).pixelBounds(width_px: 100, height_px: 100))
    }

    func testCenteredRectangle() {
        let rect = NormalizedRect.centered(width: 0.5, height: 0.8)
        XCTAssertEqual(rect.x, 0.25, accuracy: 1e-12)
        XCTAssertEqual(rect.y, 0.1, accuracy: 1e-12)
    }
}

final class CameraScaleTests: XCTestCase {
    // A 4032 × 3024 video frame (fx 3000 px) and a 640 × 480 depth map of the same field of view.
    private let video = PinholeIntrinsics(fx_px: 3000, fy_px: 3000, cx_px: 2016, cy_px: 1512,
                                          referenceWidth_px: 4032, referenceHeight_px: 3024)
    private let depth = PinholeIntrinsics(fx_px: 3000.0 * 640.0 / 4032.0, fy_px: 3000.0 * 640.0 / 4032.0,
                                          cx_px: 320, cy_px: 240, referenceWidth_px: 640, referenceHeight_px: 480)

    private func map(_ value: (Int, Int) -> Float) -> DepthMap {
        var values = [Float](repeating: 0, count: 640 * 480)
        for y in 0..<480 { for x in 0..<640 { values[y * 640 + x] = value(x, y) } }
        return DepthMap(width: 640, height: 480, values_m: values)
    }

    private func footprint(_ roi: NormalizedRect) -> DepthFootprint {
        CameraScale.footprint(roi: roi, video: video, videoSize_px: (4032, 3024), depth: depth, depthSize_px: (640, 480))!
    }

    func testFootprintOfACentredRoi() {
        let f = footprint(.centered(width: 0.5, height: 0.5))
        XCTAssertEqual(f.x0, 160, accuracy: 1)
        XCTAssertEqual(f.x1, 480, accuracy: 1)
        XCTAssertEqual(f.y0, 120, accuracy: 1)
        XCTAssertEqual(f.y1, 360, accuracy: 1)
    }

    func testFootprintOfTheWholeFrameIsTheWholeMap() {
        let f = footprint(.full)
        XCTAssertEqual(f, DepthFootprint(x0: 0, y0: 0, x1: 640, y1: 480))
    }

    func testFootprintFollowsDifferentIntrinsics() {
        // A depth camera with a wider view sees the ROI smaller.
        let wide = PinholeIntrinsics(fx_px: 300, fy_px: 300, cx_px: 320, cy_px: 240, referenceWidth_px: 640, referenceHeight_px: 480)
        let f = CameraScale.footprint(roi: .centered(width: 0.5, height: 0.5), video: video, videoSize_px: (4032, 3024),
                                      depth: wide, depthSize_px: (640, 480))!
        XCTAssertLessThan(f.x1 - f.x0, 320)
        XCTAssertEqual(Double(f.x0 + f.x1) / 2.0, 320, accuracy: 1)
    }

    func testFootprintOfAnEmptyRoiIsNil() {
        let empty = NormalizedRect(x: 0.5, y: 0.5, width: 0, height: 0)
        XCTAssertNil(CameraScale.footprint(roi: empty, video: video, videoSize_px: (4032, 3024), depth: depth,
                                           depthSize_px: (640, 480)))
        let broken = PinholeIntrinsics(fx_px: 0, fy_px: 0, cx_px: 0, cy_px: 0, referenceWidth_px: 640, referenceHeight_px: 480)
        XCTAssertNil(CameraScale.footprint(roi: .full, video: broken, videoSize_px: (4032, 3024), depth: depth,
                                           depthSize_px: (640, 480)))
    }

    func testFlatSurfaceGivesItsDistanceAndScale() {
        let flat = map { _, _ in 1.0 }
        let reading = CameraScale.reading(maps: Array(repeating: flat, count: 30),
                                          footprint: footprint(.centered(width: 0.5, height: 0.5)))
        XCTAssertEqual(reading.distance_mm ?? 0, 1000, accuracy: 0.01)
        XCTAssertEqual(reading.spread_mm ?? 1, 0, accuracy: 0.01)
        XCTAssertEqual(reading.validShare, 1, accuracy: 1e-9)
        XCTAssertTrue(reading.isValid)
        XCTAssertNil(reading.problem)
        XCTAssertEqual(CameraScale.mmPerPixel(distance_mm: 1000, fx_px: 3000) ?? 0, 1000.0 / 3000.0, accuracy: 1e-12)
    }

    func testHolesBelowHalfAreTolerated() {
        // 30 % of the pixels have no depth (every pixel with x + 2y divisible by 10 in three of ten residues).
        let holes = map { x, y in ((x + 2 * y) % 10) < 3 ? 0 : 1.2 }
        let reading = CameraScale.reading(maps: [holes, holes, holes], footprint: footprint(.centered(width: 0.5, height: 0.5)))
        XCTAssertEqual(reading.distance_mm ?? 0, 1200, accuracy: 0.01)
        XCTAssertTrue(reading.isValid)
        XCTAssertLessThan(reading.validShare, 0.8)
    }

    func testMostlyInvalidDepthIsNotAReading() {
        let mostlyHoles = map { x, y in ((x + 2 * y) % 10) < 7 ? .nan : 1.2 }
        let reading = CameraScale.reading(maps: [mostlyHoles, mostlyHoles], footprint: footprint(.centered(width: 0.5, height: 0.5)))
        XCTAssertFalse(reading.isValid)
        XCTAssertNotNil(reading.distance_mm)
        XCTAssertEqual(reading.problem, "Too few valid depth pixels in the region")
    }

    func testNoValidPixelGivesNoDistance() {
        let none = map { _, _ in .infinity }
        let reading = CameraScale.reading(maps: [none], footprint: footprint(.full))
        XCTAssertNil(reading.distance_mm)
        XCTAssertFalse(reading.isValid)
        XCTAssertEqual(reading.problem, "No valid depth in the region")
        XCTAssertFalse(CameraScale.reading(maps: [], footprint: footprint(.full)).isValid)
    }

    func testAnEdgeInTheRegionMakesTheSpreadTooLarge() {
        let step = map { x, _ in x < 320 ? 1.0 : 1.3 }
        let reading = CameraScale.reading(maps: [step, step], footprint: footprint(.full))
        XCTAssertFalse(reading.isValid)
        XCTAssertGreaterThan(reading.spread_mm ?? 0, 0.02 * (reading.distance_mm ?? 0))
        XCTAssertTrue(reading.problem?.hasPrefix("Depth varies too much") ?? false)
    }

    func testASlightTiltStaysWithinTheSpreadLimit() {
        // 1,000 mm at the left edge to 1,030 mm at the right: interquartile range 15 mm, 1.5 % of the distance.
        let tilted = map { x, _ in 1.0 + 0.03 * Float(x) / 639.0 }
        let reading = CameraScale.reading(maps: [tilted], footprint: footprint(.full))
        XCTAssertEqual(reading.distance_mm ?? 0, 1015, accuracy: 1.5)
        XCTAssertEqual(reading.spread_mm ?? 0, 15, accuracy: 1.5)
        XCTAssertTrue(reading.isValid)
    }

    func testTooFewGoodMapsIsNotAReading() {
        let good = map { _, _ in 1.0 }
        let bad = map { _, _ in .nan }
        let maps = Array(repeating: good, count: 10) + Array(repeating: bad, count: 20)
        let reading = CameraScale.reading(maps: maps, footprint: footprint(.full))
        XCTAssertEqual(reading.goodMapCount, 10)
        XCTAssertEqual(reading.mapCount, 30)
        XCTAssertFalse(reading.isValid)
    }

    func testPercentileInterpolatesLikeNumpy() {
        XCTAssertEqual(CameraScale.percentile([1, 2, 3, 4], 0.5), 2.5, accuracy: 1e-12)
        XCTAssertEqual(CameraScale.percentile([1, 2, 3, 4], 0.25), 1.75, accuracy: 1e-12)
        XCTAssertEqual(CameraScale.percentile([5], 0.75), 5, accuracy: 1e-12)
        XCTAssertEqual(CameraScale.percentile([], 0.5), 0, accuracy: 1e-12)
    }

    func testMmPerPixelNeedsPositiveValues() {
        XCTAssertNil(CameraScale.mmPerPixel(distance_mm: 0, fx_px: 3000))
        XCTAssertNil(CameraScale.mmPerPixel(distance_mm: 1000, fx_px: 0))
    }

    func testIntrinsicsScaleWithTheImageSize() {
        let half = video.scaled(width_px: 2016, height_px: 1512)
        XCTAssertEqual(half.fx_px, 1500, accuracy: 1e-9)
        XCTAssertEqual(half.cx_px, 1008, accuracy: 1e-9)
        XCTAssertEqual(half.referenceWidth_px, 2016, accuracy: 1e-9)
    }
}
