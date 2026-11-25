import Foundation

/// Small pure helpers of the probe.
enum ProbeMath {
    /// One reading of the camera's exposure and ISO while it settles.
    struct SettleSample: Equatable, Sendable {
        var time_s: Double
        var exposure_s: Double
        var iso: Double
    }

    /// Time of the first sample from which every later sample (up to the last) stays within `tolerance` (relative) of
    /// the last sample's exposure and ISO: how long the camera took to settle. nil without samples. A series that
    /// never leaves the band settles at its first sample's time.
    static func settleTime(_ samples: [SettleSample], tolerance: Double = 0.02) -> Double? {
        guard let last = samples.last else { return nil }
        func close(_ a: Double, _ b: Double) -> Bool {
            abs(a - b) <= tolerance * max(abs(b), 1e-12)
        }
        var settled = samples.count - 1
        while settled > 0 {
            let previous = samples[settled - 1]
            if close(previous.exposure_s, last.exposure_s) && close(previous.iso, last.iso) {
                settled -= 1
            } else {
                break
            }
        }
        return samples[settled].time_s
    }

    /// Relative difference `(b - a) / a`, nil when `a` is not positive.
    static func relativeChange(_ a: Double, _ b: Double) -> Double? {
        a > 0 ? (b - a) / a : nil
    }

    /// Frames per second from first and last timestamps and the number of frames (nil for fewer than two frames or no time).
    static func rate(frames: Int, first_s: Double, last_s: Double) -> Double? {
        guard frames >= 2, last_s > first_s else { return nil }
        return Double(frames - 1) / (last_s - first_s)
    }

    /// Depth-map rectangles for the distance zones: the centre and the four corners, each `share` of the map's width
    /// and height, the corners inset by `inset` of the width and height from the edges.
    static func lidarZones(width: Int, height: Int, share: Double = 0.1, inset: Double = 0.05)
        -> [(name: String, footprint: DepthFootprint)] {
        guard width > 0, height > 0 else { return [] }
        func block(_ cx: Double, _ cy: Double) -> DepthFootprint {
            let w = max(1.0, share * Double(width))
            let h = max(1.0, share * Double(height))
            let x0 = min(max(Int((cx * Double(width) - w / 2).rounded()), 0), width - 1)
            let y0 = min(max(Int((cy * Double(height) - h / 2).rounded()), 0), height - 1)
            return DepthFootprint(x0: x0, y0: y0, x1: min(width, x0 + Int(w.rounded(.up))), y1: min(height, y0 + Int(h.rounded(.up))))
        }
        let a = inset + share / 2
        return [("centre", block(0.5, 0.5)), ("top left", block(a, a)), ("top right", block(1 - a, a)),
                ("bottom left", block(a, 1 - a)), ("bottom right", block(1 - a, 1 - a))]
    }
}
