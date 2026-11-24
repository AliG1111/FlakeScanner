import XCTest

final class FlickerReadoutTests: XCTestCase {
    private let runExposure_s = 1.0 / 4200.0

    private func simulation(_ kind: FlickerWave.Kind, hz: Double, readout_ms: Double,
                            reversed: Bool = false) -> FlickerSimulation {
        FlickerSimulation(wave: FlickerWave(kind), hz: hz, readout_s: readout_ms / 1000.0, reversed: reversed)
    }

    /// Light check, then the two readout bursts at 1/(2F), as the app runs them.
    private func readoutTest(_ sim: FlickerSimulation, lightCheckExposure_s: Double? = nil,
                             seed: UInt64) -> (LightCheck, ReadoutTest) {
        var rng = PCG32(seed: seed)
        let exposure = lightCheckExposure_s ?? runExposure_s
        guard let check = FlickerReadout.lightCheck(sim.lightCheckBurst(exposure_s: exposure, rng: &rng)) else {
            XCTFail("light check returned nil")
            return (LightCheck(index: 0, flickerHz: 0, floorIndex: 0, binIndices: [], accepted: false),
                    ReadoutTest(bursts: [], readoutTime_s: nil, direction: nil, failure: "nil"))
        }
        let burstExposure = 1.0 / (2.0 * check.flickerHz)
        let bursts = (0..<2).map { _ in sim.burst(frameDuration_s: FlickerReadout.burstFrameDuration_s,
                                                  exposure_s: burstExposure, rng: &rng) }
        let test = FlickerReadout.readoutTest(lightCheck: check, lightCheckExposure_s: exposure,
                                              bursts: bursts, sensorRows: sim.rows)
        return (check, test)
    }

    // MARK: Strips

    func testStripRangesCoverTheRoiInShortStrips() {
        let ranges = FlickerReadout.stripRanges(firstRow: 330, rows: 1500)
        XCTAssertEqual(ranges.count, 47)
        XCTAssertEqual(ranges.first?.lowerBound, 330)
        XCTAssertEqual(ranges.last?.upperBound, 1830)
        for (previous, next) in zip(ranges, ranges.dropFirst()) {
            XCTAssertEqual(previous.upperBound, next.lowerBound)
        }
        XCTAssertTrue(ranges.allSatisfy { $0.count <= FlickerReadout.maxStripRows && $0.count >= 31 })
        XCTAssertEqual(ranges.reduce(0) { $0 + $1.count }, 1500)
    }

    func testStripRangesEdgeCases() {
        XCTAssertEqual(FlickerReadout.stripRanges(firstRow: 10, rows: 20), [10..<30])
        XCTAssertEqual(FlickerReadout.stripRanges(firstRow: 0, rows: 0), [])
        XCTAssertEqual(FlickerReadout.stripRanges(firstRow: 0, rows: 33).map(\.count), [17, 16])
        XCTAssertEqual(FlickerReadout.centreRows(of: [10..<14]), [11.5])
    }

    // MARK: Light check

    func testLightCheckFindsSineFlickerAtBothMainsFrequencies() {
        for (hz, mains) in [(120.0, 60.0), (100.0, 50.0)] {
            var rng = PCG32(seed: 11)
            let burst = simulation(.sine(depth: 0.3), hz: hz, readout_ms: 10).lightCheckBurst(exposure_s: runExposure_s, rng: &rng)
            let check = FlickerReadout.lightCheck(burst)
            XCTAssertNotNil(check)
            XCTAssertEqual(check?.flickerHz, hz)
            XCTAssertEqual(check?.index ?? 0, 0.3, accuracy: 0.01)
            XCTAssertEqual(check?.accepted, true)
            XCTAssertEqual(check?.mainsHz, mains)
            XCTAssertEqual(check?.isAmber, true)
        }
    }

    func testLightCheckIndexOfFullWaveRectifiedLight() {
        // |sin| has a fundamental of 2/3 of its mean.
        var rng = PCG32(seed: 12)
        let burst = simulation(.fullWave, hz: 120, readout_ms: 10).lightCheckBurst(exposure_s: runExposure_s, rng: &rng)
        let check = FlickerReadout.lightCheck(burst)
        XCTAssertEqual(check?.flickerHz, 120)
        XCTAssertEqual(check?.index ?? 0, 2.0 / 3.0, accuracy: 0.02)
        XCTAssertEqual(check?.accepted, true)
    }

    func testLightCheckFindsHalfWaveDriverAtTheMainsFrequency() {
        for mains in [50.0, 60.0] {
            var rng = PCG32(seed: 13)
            let burst = simulation(.halfWave, hz: mains, readout_ms: 10).lightCheckBurst(exposure_s: runExposure_s, rng: &rng)
            let check = FlickerReadout.lightCheck(burst)
            XCTAssertEqual(check?.flickerHz, mains)
            XCTAssertEqual(check?.accepted, true)
            XCTAssertEqual(check?.mainsHz, mains)
            // Fundamental of a half-wave rectified sine is π/2 of its mean; the check reads up to 4 % low.
            XCTAssertEqual(check?.index ?? 0, Double.pi / 2, accuracy: 0.1)
        }
    }

    func testWeakFlickerOnAStillSurfaceIsAccepted() {
        var rng = PCG32(seed: 14)
        let burst = simulation(.sine(depth: 0.05), hz: 100, readout_ms: 10).lightCheckBurst(exposure_s: runExposure_s, rng: &rng)
        let check = FlickerReadout.lightCheck(burst)
        XCTAssertEqual(check?.flickerHz, 100)
        XCTAssertEqual(check?.index ?? 0, 0.05, accuracy: 0.005)
        XCTAssertEqual(check?.accepted, true)
        XCTAssertEqual(check?.isAmber, true)
    }

    func testSteadyLightIsNotAccepted() {
        var rng = PCG32(seed: 15)
        let burst = simulation(.sine(depth: 0), hz: 120, readout_ms: 10).lightCheckBurst(exposure_s: runExposure_s, rng: &rng)
        let check = FlickerReadout.lightCheck(burst)
        XCTAssertNotNil(check)
        XCTAssertEqual(check?.accepted, false)
        XCTAssertLessThan(check?.index ?? 1, FlickerReadout.acceptMinIndex)
        XCTAssertNil(check?.mainsHz)
        XCTAssertEqual(check?.isAmber, false)
    }

    func testLightCheckNeedsExactlyOneBurst() {
        var rng = PCG32(seed: 16)
        let sim = simulation(.sine(depth: 0.3), hz: 120, readout_ms: 10)
        let short = sim.burst(frameDuration_s: FlickerReadout.burstFrameDuration_s, exposure_s: runExposure_s,
                              frames: 26, rng: &rng)
        XCTAssertNil(FlickerReadout.lightCheck(short))
        let broken = StripSeries(means: [[1, 2], [1]], centreRows_px: [0, 1])
        XCTAssertFalse(broken.isConsistent)
        XCTAssertNil(FlickerReadout.lightCheck(broken))
    }

    // MARK: Readout time

    func testFlickerBinOfTheBurst() {
        XCTAssertEqual(FlickerReadout.flickerBin(flickerHz: 100, frameDuration_s: 1.0 / 27.0, frames: 27), 19)
        XCTAssertEqual(FlickerReadout.flickerBin(flickerHz: 120, frameDuration_s: 1.0 / 27.0, frames: 27), 12)
        XCTAssertEqual(FlickerReadout.flickerBin(flickerHz: 60, frameDuration_s: 1.0 / 27.0, frames: 27), 6)
        XCTAssertEqual(FlickerReadout.flickerBin(flickerHz: 50, frameDuration_s: 1.0 / 27.0, frames: 27), 23)
    }

    func testReadoutTimeWithinThreePercentForWaveformsAndMains() {
        var seed: UInt64 = 100
        let cases: [(String, FlickerWave.Kind, Double)] = [
            ("sine", .sine(depth: 0.3), 0), ("full wave", .fullWave, 0), ("half wave", .halfWave, 1),
        ]
        for (name, kind, halfWave) in cases {
            for mains in [50.0, 60.0] {
                let hz = halfWave == 1 ? mains : 2 * mains
                for readout_ms in [5.0, 10.0, 25.0] {
                    seed += 1
                    let (check, test) = readoutTest(simulation(kind, hz: hz, readout_ms: readout_ms), seed: seed)
                    let label = "\(name) \(hz) Hz \(readout_ms) ms"
                    XCTAssertTrue(check.accepted, label)
                    XCTAssertNil(test.failure, "\(label): \(test.failure ?? "")")
                    XCTAssertEqual(test.direction, 1, label)
                    let measured = (test.readoutTime_s ?? 0) * 1000.0
                    XCTAssertEqual(measured, readout_ms, accuracy: 0.03 * readout_ms, label)
                    for burst in test.bursts {
                        XCTAssertTrue(burst.failedChecks.isEmpty, "\(label): \(burst.failedChecks)")
                        XCTAssertEqual(burst.amplitudeRatio ?? 0, 1.0, accuracy: 0.2, label)
                        XCTAssertLessThanOrEqual(burst.fit?.residual_rad ?? 9, FlickerReadout.maxResidual_rad, label)
                    }
                }
            }
        }
    }

    func testReadoutDirectionFollowsTheSignOfTheSlope() {
        let (_, test) = readoutTest(simulation(.sine(depth: 0.3), hz: 120, readout_ms: 12, reversed: true), seed: 200)
        XCTAssertNil(test.failure)
        XCTAssertEqual(test.direction, -1)
        XCTAssertEqual((test.readoutTime_s ?? 0) * 1000.0, 12.0, accuracy: 0.36)
        for burst in test.bursts {
            XCTAssertEqual(burst.fit?.direction, -1)
        }
    }

    func testReadoutPassesWhenTheLightCheckRanAtALongExposure() {
        // At 1/278 s the light check's own exposure has weakened the index by sinc(F t) = 0.72 at 120 Hz.
        let sim = simulation(.sine(depth: 0.3), hz: 120, readout_ms: 15)
        let exposure = 1.0 / 278.0
        let (check, test) = readoutTest(sim, lightCheckExposure_s: exposure, seed: 300)
        XCTAssertEqual(check.index, 0.3 * FlickerReadout.sinc(120 * exposure), accuracy: 0.01)
        XCTAssertNil(test.failure, test.failure ?? "")
        XCTAssertEqual((test.readoutTime_s ?? 0) * 1000.0, 15.0, accuracy: 0.45)
        for burst in test.bursts {
            XCTAssertEqual(burst.amplitudeRatio ?? 0, 1.0, accuracy: 0.2)
        }
    }

    func testFastPwmThatLooksLikeMainsFlickerFailsTheAmplitudeCheck() {
        // 1,200 Hz aliases into the 120 Hz bin of the light check, but the readout burst's exposure of 1/240 s spans
        // five of its periods and removes it.
        let (check, test) = readoutTest(simulation(.sine(depth: 0.3), hz: 1200, readout_ms: 10), seed: 400)
        XCTAssertNotNil(test.failure)
        XCTAssertNil(test.readoutTime_s)
        XCTAssertNil(test.direction)
        if check.accepted {
            XCTAssertEqual(test.failure, FlickerReadout.unsuitableLightMessage)
            for burst in test.bursts {
                XCTAssertLessThan(burst.amplitudeRatio ?? 1, FlickerReadout.amplitudeRatioBand.lowerBound)
                XCTAssertTrue(burst.failedChecks.contains("amplitude"))
            }
        }
    }

    func testReadoutTestNeedsAnAcceptedFlickerFrequency() {
        var rng = PCG32(seed: 500)
        let sim = simulation(.sine(depth: 0), hz: 120, readout_ms: 10)
        let check = FlickerReadout.lightCheck(sim.lightCheckBurst(exposure_s: runExposure_s, rng: &rng))
        XCTAssertEqual(check?.accepted, false)
        let burst = sim.burst(frameDuration_s: FlickerReadout.burstFrameDuration_s, exposure_s: 1.0 / 240.0, rng: &rng)
        let test = FlickerReadout.readoutTest(lightCheck: check!, lightCheckExposure_s: runExposure_s,
                                              bursts: [burst, burst], sensorRows: 2160)
        XCTAssertNotNil(test.failure)
        XCTAssertNil(test.readoutTime_s)
        XCTAssertTrue(test.bursts.isEmpty)
    }

    func testReadoutTestNeedsTwoBursts() {
        var rng = PCG32(seed: 501)
        let sim = simulation(.sine(depth: 0.3), hz: 120, readout_ms: 10)
        let check = FlickerReadout.lightCheck(sim.lightCheckBurst(exposure_s: runExposure_s, rng: &rng))!
        let burst = sim.burst(frameDuration_s: FlickerReadout.burstFrameDuration_s, exposure_s: 1.0 / 240.0, rng: &rng)
        let test = FlickerReadout.readoutTest(lightCheck: check, lightCheckExposure_s: runExposure_s,
                                              bursts: [burst], sensorRows: 2160)
        XCTAssertEqual(test.failure, "The readout test needs two bursts")
    }

    func testSinc() {
        XCTAssertEqual(FlickerReadout.sinc(0), 1, accuracy: 1e-12)
        XCTAssertEqual(FlickerReadout.sinc(0.5), 2.0 / Double.pi, accuracy: 1e-12)
        XCTAssertEqual(FlickerReadout.sinc(1), 0, accuracy: 1e-12)
        XCTAssertEqual(FlickerReadout.sinc(-0.5), 2.0 / Double.pi, accuracy: 1e-12)
    }
}
