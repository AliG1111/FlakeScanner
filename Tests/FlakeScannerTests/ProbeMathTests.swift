import XCTest

final class ProbeMathTests: XCTestCase {
    private func sample(_ t: Double, _ e: Double, _ iso: Double) -> ProbeMath.SettleSample {
        ProbeMath.SettleSample(time_s: t, exposure_s: e, iso: iso)
    }

    func testSettleTimeIsTheStartOfTheFinalSteadyRun() {
        let samples = [sample(0.0, 0.01, 100), sample(0.1, 0.02, 200), sample(0.2, 0.005, 400),
                       sample(0.3, 0.00405, 401), sample(0.4, 0.004, 400), sample(0.5, 0.004, 400)]
        XCTAssertEqual(ProbeMath.settleTime(samples), 0.3)
    }

    func testSettleTimeOfASteadySeriesIsItsStart() {
        XCTAssertEqual(ProbeMath.settleTime([sample(1.0, 0.004, 400), sample(1.1, 0.004, 400)]), 1.0)
        XCTAssertEqual(ProbeMath.settleTime([sample(2.5, 0.004, 400)]), 2.5)
        XCTAssertNil(ProbeMath.settleTime([]))
    }

    func testSettleTimeWhenOnlyTheLastSampleDiffers() {
        let samples = [sample(0, 0.01, 100), sample(0.1, 0.01, 100), sample(0.2, 0.02, 100)]
        XCTAssertEqual(ProbeMath.settleTime(samples), 0.2)
    }

    func testRelativeChangeAndRate() {
        XCTAssertEqual(ProbeMath.relativeChange(100, 103) ?? 0, 0.03, accuracy: 1e-12)
        XCTAssertNil(ProbeMath.relativeChange(0, 1))
        XCTAssertEqual(ProbeMath.rate(frames: 31, first_s: 5, last_s: 6) ?? 0, 30, accuracy: 1e-9)
        XCTAssertNil(ProbeMath.rate(frames: 1, first_s: 5, last_s: 6))
        XCTAssertNil(ProbeMath.rate(frames: 5, first_s: 6, last_s: 6))
    }

    func testLidarZonesAreInsideTheMapAndDistinct() {
        let zones = ProbeMath.lidarZones(width: 640, height: 480)
        XCTAssertEqual(zones.map(\.name), ["centre", "top left", "top right", "bottom left", "bottom right"])
        for zone in zones {
            XCTAssertGreaterThanOrEqual(zone.footprint.x0, 0)
            XCTAssertGreaterThanOrEqual(zone.footprint.y0, 0)
            XCTAssertLessThanOrEqual(zone.footprint.x1, 640)
            XCTAssertLessThanOrEqual(zone.footprint.y1, 480)
            XCTAssertGreaterThan(zone.footprint.area, 0)
        }
        XCTAssertEqual(zones[0].footprint, DepthFootprint(x0: 288, y0: 216, x1: 352, y1: 264))
        XCTAssertLessThan(zones[1].footprint.x1, zones[2].footprint.x0)
        XCTAssertTrue(ProbeMath.lidarZones(width: 0, height: 480).isEmpty)
    }
}
