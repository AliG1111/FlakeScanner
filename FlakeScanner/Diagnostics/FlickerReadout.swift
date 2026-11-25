import Foundation

/// Brightness of the strips of the region of interest over a burst of frames: `means[frame][strip]`, in any linear
/// brightness scale, and the centre row of each strip in sensor rows (the readout direction).
struct StripSeries: Equatable, Sendable {
    var means: [[Double]]
    var centreRows_px: [Double]

    var frameCount: Int { means.count }
    var stripCount: Int { centreRows_px.count }

    /// At least one strip, every frame has one value per strip, and all values are finite.
    var isConsistent: Bool {
        guard stripCount >= 1, frameCount >= 1 else { return false }
        return means.allSatisfy { $0.count == stripCount && $0.allSatisfy { $0.isFinite } }
    }
}

/// One DFT bin of the 27-frame burst that carries a flicker frequency (design §6.16).
struct FlickerBin: Equatable, Sendable {
    var bin: Int
    var hz: Double
}

/// Result of the light check (design §6.16): strongest flicker bin of the strips' brightness over a burst.
struct LightCheck: Codable, Equatable, Sendable {
    /// Root mean square over the strips of the amplitude in the strongest of the four bins, relative to the mean
    /// brightness (0.3 for 30 % flicker).
    var index: Double
    /// Flicker frequency of the strongest bin: 50, 60, 100 or 120 Hz.
    var flickerHz: Double
    /// Median over the other bins of the same amplitude (the light's harmonics, the texture and the noise).
    var floorIndex: Double
    /// Index of each of the four flicker bins, in the order of `FlickerReadout.flickerBins`.
    var binIndices: [Double]
    /// The frequency is trusted: index at least 3 × floor and at least 0.01.
    var accepted: Bool

    /// 50 or 60 Hz when accepted (100 and 50 Hz mean 50 Hz mains, 120 and 60 Hz mean 60 Hz), otherwise nil.
    var mainsHz: Double? {
        guard accepted else { return nil }
        return (flickerHz == 50 || flickerHz == 100) ? 50 : 60
    }

    /// Above 0.03 the quality light turns amber with "Light flickers" (provisional until the probe).
    var isAmber: Bool { accepted && index > FlickerReadout.amberIndex }
}

/// A straight-line fit of the flicker's phase against the strip rows in one burst.
struct ReadoutFit: Codable, Equatable, Sendable {
    /// Rows × t_line: the time to read the whole frame.
    var readoutTime_s: Double
    /// Time from one row to the next.
    var lineTime_s: Double
    /// +1 when the rows are read in +y order (top to bottom of the buffer), −1 when in the opposite order.
    var direction: Int
    /// |X|²-weighted RMS residual of the phase line.
    var residual_rad: Double
    /// The burst's amplitude at the light check's flicker bin, relative to the mean brightness.
    var binIndex: Double
}

/// One readout burst with its three checks.
struct ReadoutBurstResult: Codable, Equatable, Sendable {
    var fit: ReadoutFit?
    /// Bin amplitude over (2/π) × the light-check index ÷ sinc(F · t_lc); about 1 for one light at the flicker frequency.
    var amplitudeRatio: Double?
    /// Names of the checks that failed (empty: the burst is usable).
    var failedChecks: [String]
}

/// The readout test: two bursts (the second with the phone turned 180°), their mean and the verdict.
struct ReadoutTest: Codable, Equatable, Sendable {
    var bursts: [ReadoutBurstResult]
    /// Mean of the bursts' readout times, nil when the test failed.
    var readoutTime_s: Double?
    /// +1 / −1 as `ReadoutFit.direction`, nil when the test failed.
    var direction: Int?
    /// Why the test failed, nil when it passed.
    var failure: String?
}

/// Pure light check and readout-time test (design §6.16). The only owner of the flicker index; the probe
/// (P0.7) and the light check at Start (P3.1) feed it strip means, so the device code stays out of the maths.
enum FlickerReadout {
    /// Frames of a burst: 27 frames at 1/27 s are exactly 100 or 120 flicker periods, so the burst samples 27 or 9
    /// evenly spaced phases and puts 100 / 120 Hz into DFT bins 8 / 12 (50 / 60 Hz half-wave drivers into 4 / 6).
    static let burstFrames = 27
    static let burstFrameDuration_s = 1.0 / 27.0
    /// A strip is short enough to see one phase of the light (a whole ROI can span close to a whole flicker period).
    static let maxStripRows = 32
    static let flickerBins: [FlickerBin] = [
        FlickerBin(bin: 4, hz: 50), FlickerBin(bin: 6, hz: 60), FlickerBin(bin: 8, hz: 100), FlickerBin(bin: 12, hz: 120),
    ]
    /// The frequency is accepted when the index is at least this many times the median of the other bins …
    static let acceptRatio = 3.0
    /// … and at least this index (steady light on a moving or shaking surface reaches 0.018 at most).
    static let acceptMinIndex = 0.01
    /// Quality light amber above this index (provisional, confirmed by the probe).
    static let amberIndex = 0.03
    /// Readout check: T_r at most the frame duration less this margin.
    static let readoutMargin_s = 0.002
    /// Readout check: allowed ratio of the burst's bin amplitude to its expectation.
    static let amplitudeRatioBand = 0.8...1.2
    /// Readout check: the phase line's weighted RMS residual at most this.
    static let maxResidual_rad = 0.25
    /// Message of the failed readout test (design §6.16).
    static let unsuitableLightMessage = "Light unsuitable for the readout test (fast PWM or uneven light)"

    // MARK: Strips

    /// Splits `rows` ROI rows (starting at `firstRow`) into strips of at most `maxRows` rows, as equal as possible
    /// (the first `rows % count` strips are one row longer, like numpy's `array_split`). Returns the half-open row
    /// ranges in sensor rows.
    static func stripRanges(firstRow: Int, rows: Int, maxRows: Int = maxStripRows) -> [Range<Int>] {
        guard rows > 0, maxRows > 0 else { return [] }
        let count = (rows + maxRows - 1) / maxRows
        let base = rows / count
        let extra = rows % count
        var ranges: [Range<Int>] = []
        var start = firstRow
        for index in 0..<count {
            let length = base + (index < extra ? 1 : 0)
            ranges.append(start..<(start + length))
            start += length
        }
        return ranges
    }

    /// Centre row of each strip range (between its first and last row).
    static func centreRows(of ranges: [Range<Int>]) -> [Double] {
        ranges.map { 0.5 * Double($0.lowerBound + $0.upperBound - 1) }
    }

    // MARK: Light check

    /// The light check of a burst of exactly `burstFrames` frames. Per strip: remove the linear trend over the
    /// frames, take the one-sided DFT amplitude 2|X|/n, root mean square over the strips relative to the mean
    /// brightness; the strongest of the bins 4, 6, 8, 12 is the flicker, the median of the other bins 1…13 the floor.
    /// Returns nil for a burst of another length or without usable brightness.
    static func lightCheck(_ series: StripSeries) -> LightCheck? {
        let n = series.frameCount
        guard n == burstFrames, series.isConsistent else { return nil }
        let amplitudes = binAmplitudes(series, detrend: true)
        guard let overall = meanBrightness(series), overall > 0 else { return nil }
        let relative = amplitudes.map { $0 / overall }
        var bestBin = flickerBins[0]
        for candidate in flickerBins where relative[candidate.bin] > relative[bestBin.bin] {
            bestBin = candidate
        }
        let flickerBinNumbers = Set(flickerBins.map(\.bin))
        let others = (1...(n / 2)).filter { !flickerBinNumbers.contains($0) }.map { relative[$0] }
        let floor = median(others)
        let index = relative[bestBin.bin]
        return LightCheck(index: index,
                          flickerHz: bestBin.hz,
                          floorIndex: floor,
                          binIndices: flickerBins.map { relative[$0.bin] },
                          accepted: index >= acceptRatio * floor && index >= acceptMinIndex)
    }

    /// Root-mean-square over the strips of the one-sided amplitude of each DFT bin `0...n/2` (index 0 is unused: 0).
    private static func binAmplitudes(_ series: StripSeries, detrend: Bool) -> [Double] {
        let n = series.frameCount
        let strips = series.stripCount
        let half = n / 2
        var cosTable = [[Double]](repeating: [Double](repeating: 0, count: n), count: half + 1)
        var sinTable = cosTable
        for bin in 1...half {
            for k in 0..<n {
                let angle = 2.0 * Double.pi * Double(bin) * Double(k) / Double(n)
                cosTable[bin][k] = cos(angle)
                sinTable[bin][k] = sin(angle)
            }
        }
        var sumSquares = [Double](repeating: 0, count: half + 1)
        for strip in 0..<strips {
            var y = series.means.map { $0[strip] }
            if detrend { removeLinearTrend(&y) }
            for bin in 1...half {
                var re = 0.0
                var im = 0.0
                for k in 0..<n {
                    re += y[k] * cosTable[bin][k]
                    im -= y[k] * sinTable[bin][k]
                }
                let amplitude = 2.0 * (re * re + im * im).squareRoot() / Double(n)
                sumSquares[bin] += amplitude * amplitude
            }
        }
        return sumSquares.map { ($0 / Double(strips)).squareRoot() }
    }

    private static func removeLinearTrend(_ y: inout [Double]) {
        let n = Double(y.count)
        let meanK = (n - 1) / 2
        let meanY = y.reduce(0, +) / n
        var num = 0.0
        var den = 0.0
        for (k, value) in y.enumerated() {
            let dk = Double(k) - meanK
            num += dk * (value - meanY)
            den += dk * dk
        }
        let slope = den > 0 ? num / den : 0
        for k in 0..<y.count {
            y[k] -= meanY + slope * (Double(k) - meanK)
        }
    }

    private static func meanBrightness(_ series: StripSeries) -> Double? {
        let count = series.frameCount * series.stripCount
        guard count > 0 else { return nil }
        var total = 0.0
        for frame in series.means { for value in frame { total += value } }
        return total / Double(count)
    }

    private static func median(_ values: [Double]) -> Double {
        guard !values.isEmpty else { return 0 }
        let sorted = values.sorted()
        let mid = sorted.count / 2
        return sorted.count % 2 == 1 ? sorted[mid] : 0.5 * (sorted[mid - 1] + sorted[mid])
    }

    // MARK: Readout phase

    /// The DFT bin the flicker of `flickerHz` falls into at `frameDuration_s` (aliased, positive frequency).
    static func flickerBin(flickerHz: Double, frameDuration_s: Double, frames: Int) -> Int {
        let cycles = flickerHz * frameDuration_s
        let fraction = cycles - cycles.rounded(.down)
        return Int((fraction * Double(frames)).rounded()) % frames
    }

    /// Readout time by the phase slope: per strip the DFT over the frames (mean removed, Hann window) at the
    /// flicker's bin, the phase unwrapped along the strips and a straight line fitted to the strip centre rows with
    /// weights |X|². The slope is 2π · F · t_line per row, positive when the rows are read top to bottom.
    /// `sensorRows` is the number of rows of the whole frame (the readout runs over all of them).
    static func readoutFit(_ series: StripSeries, flickerHz: Double, frameDuration_s: Double,
                           sensorRows: Int) -> ReadoutFit? {
        let n = series.frameCount
        let strips = series.stripCount
        guard n == burstFrames, series.isConsistent, strips >= 3, sensorRows > 0, flickerHz > 0,
              let overall = meanBrightness(series), overall > 0 else { return nil }
        let bin = flickerBin(flickerHz: flickerHz, frameDuration_s: frameDuration_s, frames: n)
        guard bin != 0 else { return nil }
        let window = (0..<n).map { 0.5 - 0.5 * cos(2.0 * Double.pi * Double($0 + 1) / Double(n + 1)) }
        var phases = [Double](repeating: 0, count: strips)
        var weights = [Double](repeating: 0, count: strips)
        for strip in 0..<strips {
            let mean = series.means.reduce(0.0) { $0 + $1[strip] } / Double(n)
            var re = 0.0
            var im = 0.0
            for k in 0..<n {
                let value = (series.means[k][strip] - mean) * window[k]
                let angle = 2.0 * Double.pi * Double(bin) * Double(k) / Double(n)
                re += value * cos(angle)
                im -= value * sin(angle)
            }
            phases[strip] = atan2(im, re)
            weights[strip] = (re * re + im * im).squareRoot()
        }
        // Unwrap along the strips (like numpy.unwrap with a discontinuity of π).
        for i in 1..<strips {
            let jump = phases[i] - phases[i - 1]
            phases[i] = phases[i - 1] + (jump - 2.0 * Double.pi * (jump / (2.0 * Double.pi)).rounded())
        }
        var sw = 0.0, sc = 0.0, scc = 0.0, sp = 0.0, scp = 0.0
        for i in 0..<strips {
            let w2 = weights[i] * weights[i]
            let c = series.centreRows_px[i]
            sw += w2
            sc += w2 * c
            scc += w2 * c * c
            sp += w2 * phases[i]
            scp += w2 * c * phases[i]
        }
        let denominator = sw * scc - sc * sc
        guard sw > 0, denominator > 0 else { return nil }
        let slope = (sw * scp - sc * sp) / denominator
        let intercept = (sp - slope * sc) / sw
        var residualSum = 0.0
        for i in 0..<strips {
            let residual = phases[i] - (slope * series.centreRows_px[i] + intercept)
            residualSum += weights[i] * weights[i] * residual * residual
        }
        let lineTime = abs(slope) / (2.0 * Double.pi * flickerHz)
        let amplitudes = binAmplitudes(series, detrend: true)
        let hzIndex = flickerBins.first { $0.hz == flickerHz }?.bin
        let binIndex = hzIndex.map { amplitudes[$0] / overall } ?? 0
        return ReadoutFit(readoutTime_s: lineTime * Double(sensorRows),
                          lineTime_s: lineTime,
                          direction: slope > 0 ? 1 : -1,
                          residual_rad: (residualSum / sw).squareRoot(),
                          binIndex: binIndex)
    }

    /// sin(πx) / (πx): how much an exposure of `x / F` seconds weakens a flicker of F Hz.
    static func sinc(_ x: Double) -> Double {
        abs(x) < 1e-12 ? 1 : sin(Double.pi * x) / (Double.pi * x)
    }

    // MARK: Readout test

    /// The readout test: each burst (taken at `frameDuration_s`, exposure 1/(2F), the second with the phone turned
    /// 180°) is fitted and checked; the readout time is the mean of the bursts. A failed check stops the test with
    /// `unsuitableLightMessage`. `lightCheckExposure_s` is the exposure of the light check that gave `lightCheck`
    /// (it weakened the index by sinc(F · t)).
    static func readoutTest(lightCheck: LightCheck, lightCheckExposure_s: Double, bursts: [StripSeries],
                            frameDuration_s: Double = burstFrameDuration_s, sensorRows: Int) -> ReadoutTest {
        guard lightCheck.accepted, lightCheck.index >= acceptMinIndex else {
            return ReadoutTest(bursts: [], readoutTime_s: nil, direction: nil,
                               failure: "No steady flicker frequency found (light check index \(Num.fixed(lightCheck.index, 3)))")
        }
        guard bursts.count == 2 else {
            return ReadoutTest(bursts: [], readoutTime_s: nil, direction: nil,
                               failure: "The readout test needs two bursts")
        }
        let weakening = sinc(lightCheck.flickerHz * lightCheckExposure_s)
        let expectedIndex = (2.0 / Double.pi) * lightCheck.index / max(weakening, 1e-6)
        var results: [ReadoutBurstResult] = []
        for burst in bursts {
            guard let fit = readoutFit(burst, flickerHz: lightCheck.flickerHz, frameDuration_s: frameDuration_s,
                                       sensorRows: sensorRows) else {
                results.append(ReadoutBurstResult(fit: nil, amplitudeRatio: nil, failedChecks: ["fit"]))
                continue
            }
            let ratio = expectedIndex > 0 ? fit.binIndex / expectedIndex : 0
            var failed: [String] = []
            if fit.readoutTime_s > frameDuration_s - readoutMargin_s { failed.append("readout time") }
            if !amplitudeRatioBand.contains(ratio) { failed.append("amplitude") }
            if fit.residual_rad > maxResidual_rad { failed.append("residual") }
            results.append(ReadoutBurstResult(fit: fit, amplitudeRatio: ratio, failedChecks: failed))
        }
        let fits = results.compactMap(\.fit)
        if results.contains(where: { !$0.failedChecks.isEmpty }) || fits.count != 2 {
            return ReadoutTest(bursts: results, readoutTime_s: nil, direction: nil, failure: unsuitableLightMessage)
        }
        if fits[0].direction != fits[1].direction {
            return ReadoutTest(bursts: results, readoutTime_s: nil, direction: nil,
                               failure: "The two bursts disagree on the readout direction")
        }
        let mean = (fits[0].readoutTime_s + fits[1].readoutTime_s) / 2
        return ReadoutTest(bursts: results, readoutTime_s: mean, direction: fits[0].direction, failure: nil)
    }
}
