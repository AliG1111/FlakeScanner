import Foundation

/// Seeded PCG32 generator for the tests (no system randomness: the tests must give the same numbers every run).
struct PCG32 {
    private var state: UInt64 = 0
    private let increment: UInt64

    init(seed: UInt64, sequence: UInt64 = 54) {
        increment = (sequence << 1) | 1
        _ = next()
        state = state &+ seed
        _ = next()
    }

    mutating func next() -> UInt32 {
        let old = state
        state = old &* 6364136223846793005 &+ increment
        let xorShifted = UInt32(truncatingIfNeeded: ((old >> 18) ^ old) >> 27)
        let rotation = UInt32(truncatingIfNeeded: old >> 59)
        return (xorShifted >> rotation) | (xorShifted << ((~rotation &+ 1) & 31))
    }

    /// Uniform in [0, 1).
    mutating func uniform() -> Double {
        Double(next()) / 4294967296.0
    }

    /// Standard normal (Box–Muller).
    mutating func gaussian() -> Double {
        let u1 = max(uniform(), 1e-12)
        let u2 = uniform()
        return (-2.0 * log(u1)).squareRoot() * cos(2.0 * Double.pi * u2)
    }
}

/// One period of a flicker waveform (mean 1), as in the lab's E13: the light a sensor row collects over its exposure.
struct FlickerWave {
    enum Kind {
        /// 1 + depth · cos.
        case sine(depth: Double)
        /// Full-wave rectified sine: the flicker frequency is twice the mains.
        case fullWave
        /// Half-wave rectified sine: the flicker frequency is the mains.
        case halfWave
    }

    static let tableSize = 4096
    private let cumulative: [Double]

    init(_ kind: Kind) {
        let n = FlickerWave.tableSize
        var table = (0..<n).map { index -> Double in
            let phase = (Double(index) + 0.5) / Double(n)
            switch kind {
            case .sine(let depth): return 1.0 + depth * cos(2.0 * Double.pi * phase)
            case .fullWave: return abs(sin(Double.pi * phase))
            case .halfWave: return max(0, sin(2.0 * Double.pi * phase))
            }
        }
        let mean = table.reduce(0, +) / Double(n)
        table = table.map { $0 / mean }
        var cum = [0.0]
        for value in table { cum.append(cum[cum.count - 1] + value / Double(n)) }
        cumulative = cum
    }

    private func integral(_ phase: Double) -> Double {
        let n = FlickerWave.tableSize
        let whole = phase.rounded(.down)
        let position = (phase - whole) * Double(n)
        let index = min(Int(position), n - 1)
        let fraction = position - Double(index)
        return whole + cumulative[index] + fraction * (cumulative[index + 1] - cumulative[index])
    }

    /// Light over [t, t + exposure] relative to its mean, for a flicker of `hz`.
    func light(hz: Double, time_s: Double, exposure_s: Double) -> Double {
        let a = hz * time_s
        let b = a + hz * exposure_s
        return (integral(b) - integral(a)) / (b - a)
    }
}

/// A simulated burst of 27 frames of a still, slightly textured surface under flickering light, read out row by row.
struct FlickerSimulation {
    var wave: FlickerWave
    var hz: Double
    /// Time to read all rows, s.
    var readout_s: Double
    var rows = 2160
    var roiRows = 330..<1830
    /// Rows are read from the bottom of the buffer to the top.
    var reversed = false
    var texture = 0.01
    var noise = 5e-4

    /// Strip means of one burst with the given frame duration and exposure.
    func burst(frameDuration_s: Double, exposure_s: Double, frames: Int = FlickerReadout.burstFrames,
               rng: inout PCG32) -> StripSeries {
        let ranges = FlickerReadout.stripRanges(firstRow: roiRows.lowerBound, rows: roiRows.count)
        let centres = FlickerReadout.centreRows(of: ranges)
        let centre = Double(rows - 1) / 2
        // A fixed vignette times a smooth random texture (the same in every frame: the surface is still).
        var texturePerRow = [Double](repeating: 0, count: rows)
        var walk = 0.0
        for row in 0..<rows {
            walk = 0.9 * walk + rng.gaussian()
            texturePerRow[row] = walk
        }
        let scale = texturePerRow.map { $0 * $0 }.reduce(0, +) / Double(rows)
        let surface = (0..<rows).map { row -> Double in
            let y = (Double(row) - centre) / centre
            return (1.0 - 0.3 * y * y) * (1.0 + texture * texturePerRow[row] / max(scale.squareRoot(), 1e-9))
        }
        let stripSurface = ranges.map { range in range.map { surface[$0] }.reduce(0, +) / Double(range.count) }
        let start = rng.uniform()
        var means: [[Double]] = []
        for k in 0..<frames {
            var frame: [Double] = []
            for (index, row) in centres.enumerated() {
                let rowOrder = reversed ? Double(rows - 1) - row : row
                let time = start + Double(k) * frameDuration_s + rowOrder * readout_s / Double(rows)
                let light = wave.light(hz: hz, time_s: time, exposure_s: exposure_s)
                frame.append(stripSurface[index] * light * (1.0 + noise * rng.gaussian()))
            }
            means.append(frame)
        }
        return StripSeries(means: means, centreRows_px: centres)
    }

    /// The light check burst (27 frames at 1/27 s at the exposure of the run).
    func lightCheckBurst(exposure_s: Double, rng: inout PCG32) -> StripSeries {
        burst(frameDuration_s: FlickerReadout.burstFrameDuration_s, exposure_s: exposure_s, rng: &rng)
    }
}
