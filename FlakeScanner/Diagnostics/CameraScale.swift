import Foundation

/// Pinhole intrinsics of a camera image, in pixels of a reference size (the size the matrix was calibrated for).
struct PinholeIntrinsics: Codable, Equatable, Sendable {
    var fx_px: Double
    var fy_px: Double
    var cx_px: Double
    var cy_px: Double
    var referenceWidth_px: Double
    var referenceHeight_px: Double

    /// The same camera for an image of `width_px` × `height_px` (a plain scaling of the reference size).
    func scaled(width_px: Double, height_px: Double) -> PinholeIntrinsics {
        guard referenceWidth_px > 0, referenceHeight_px > 0 else { return self }
        let sx = width_px / referenceWidth_px
        let sy = height_px / referenceHeight_px
        return PinholeIntrinsics(fx_px: fx_px * sx, fy_px: fy_px * sy, cx_px: cx_px * sx, cy_px: cy_px * sy,
                                 referenceWidth_px: width_px, referenceHeight_px: height_px)
    }
}

/// A depth map in metres along the optical axis (`DepthFloat32`), row-major; invalid pixels are NaN, infinite or ≤ 0.
struct DepthMap: Sendable {
    var width: Int
    var height: Int
    var values_m: [Float]

    var isConsistent: Bool { width > 0 && height > 0 && values_m.count == width * height }
}

/// A rectangle of depth pixels `[x0, x1) × [y0, y1)`.
struct DepthFootprint: Codable, Equatable, Sendable {
    var x0: Int
    var y0: Int
    var x1: Int
    var y1: Int

    var area: Int { max(0, x1 - x0) * max(0, y1 - y0) }
}

/// Median distance of a footprint over a series of depth maps, with the checks of design §6.17.
struct DistanceReading: Codable, Equatable, Sendable {
    /// Median depth along the optical axis, mm; nil when no pixel was valid.
    var distance_mm: Double?
    /// Interquartile range of the samples, mm.
    var spread_mm: Double?
    /// Maps that were used, and how many of them had at least half of the footprint valid.
    var mapCount: Int
    var goodMapCount: Int
    /// Share of valid pixels over all maps.
    var validShare: Double
    /// The checks passed: at least half the footprint valid in at least two thirds of the maps, spread at most 2 %.
    var isValid: Bool
    /// Why the reading does not count, nil when it does.
    var problem: String?
}

/// Pure helpers for the distance and the scale from the LiDAR (design §6.17).
enum CameraScale {
    /// A valid share of the footprint of at least this in a map makes the map good.
    static let minValidShare = 0.5
    /// A reading counts when this share of the maps is good.
    static let minGoodMapShare = 2.0 / 3.0
    /// Largest spread (interquartile range) over the distance for a reading to count.
    static let maxSpreadShare = 0.02
    /// At most this many samples are taken per map (a fixed stride, so the result is deterministic).
    static let maxSamplesPerMap = 4000

    /// Maps the ROI into the depth map: corners of the ROI in the video frame (`videoSize_px`) → direction
    /// ratios x/z, y/z through the video intrinsics → depth pixels through the depth intrinsics (the few centimetres
    /// between the lenses are ignored; they only shift the footprint on a flat mat). The result is clipped to the
    /// map and at least one pixel; nil when the ROI is empty or the intrinsics are unusable.
    static func footprint(roi: NormalizedRect,
                          video: PinholeIntrinsics, videoSize_px: (width: Int, height: Int),
                          depth: PinholeIntrinsics, depthSize_px: (width: Int, height: Int)) -> DepthFootprint? {
        guard let box = roi.pixelBounds(width_px: videoSize_px.width, height_px: videoSize_px.height),
              depthSize_px.width > 0, depthSize_px.height > 0 else { return nil }
        let v = video.scaled(width_px: Double(videoSize_px.width), height_px: Double(videoSize_px.height))
        let d = depth.scaled(width_px: Double(depthSize_px.width), height_px: Double(depthSize_px.height))
        guard v.fx_px > 0, v.fy_px > 0, d.fx_px > 0, d.fy_px > 0 else { return nil }
        let corners = [(box.x0, box.y0), (box.x1, box.y0), (box.x0, box.y1), (box.x1, box.y1)]
        var minX = Double.infinity, maxX = -Double.infinity, minY = Double.infinity, maxY = -Double.infinity
        for (px, py) in corners {
            let nx = (Double(px) - v.cx_px) / v.fx_px
            let ny = (Double(py) - v.cy_px) / v.fy_px
            let u = nx * d.fx_px + d.cx_px
            let w = ny * d.fy_px + d.cy_px
            minX = min(minX, u); maxX = max(maxX, u)
            minY = min(minY, w); maxY = max(maxY, w)
        }
        guard minX.isFinite, maxX.isFinite, minY.isFinite, maxY.isFinite else { return nil }
        let x0 = min(max(Int(minX.rounded(.down)), 0), depthSize_px.width - 1)
        let y0 = min(max(Int(minY.rounded(.down)), 0), depthSize_px.height - 1)
        let x1 = min(max(Int(maxX.rounded(.up)), x0 + 1), depthSize_px.width)
        let y1 = min(max(Int(maxY.rounded(.up)), y0 + 1), depthSize_px.height)
        return DepthFootprint(x0: x0, y0: y0, x1: x1, y1: y1)
    }

    /// Median distance and spread of the footprint over `maps` (all of one size). Depth along the optical axis, in mm.
    static func reading(maps: [DepthMap], footprint: DepthFootprint) -> DistanceReading {
        var samples: [Double] = []
        var good = 0
        var used = 0
        var validTotal = 0
        var pixelTotal = 0
        for map in maps where map.isConsistent {
            let x0 = max(0, footprint.x0), x1 = min(map.width, footprint.x1)
            let y0 = max(0, footprint.y0), y1 = min(map.height, footprint.y1)
            guard x1 > x0, y1 > y0 else { continue }
            used += 1
            let area = (x1 - x0) * (y1 - y0)
            let stride = max(1, Int((Double(area) / Double(maxSamplesPerMap)).squareRoot().rounded(.up)))
            var seen = 0
            var valid = 0
            var y = y0
            while y < y1 {
                var x = x0
                while x < x1 {
                    seen += 1
                    let value = map.values_m[y * map.width + x]
                    if value.isFinite, value > 0 {
                        valid += 1
                        samples.append(Double(value) * 1000.0)
                    }
                    x += stride
                }
                y += stride
            }
            validTotal += valid
            pixelTotal += seen
            if seen > 0, Double(valid) / Double(seen) >= minValidShare { good += 1 }
        }
        let validShare = pixelTotal > 0 ? Double(validTotal) / Double(pixelTotal) : 0
        guard used > 0, !samples.isEmpty else {
            return DistanceReading(distance_mm: nil, spread_mm: nil, mapCount: used, goodMapCount: good,
                                   validShare: validShare, isValid: false,
                                   problem: "No valid depth in the region")
        }
        samples.sort()
        let median = percentile(samples, 0.5)
        let spread = percentile(samples, 0.75) - percentile(samples, 0.25)
        var problem: String?
        if Double(good) < minGoodMapShare * Double(used) {
            problem = "Too few valid depth pixels in the region"
        } else if spread > maxSpreadShare * median {
            problem = "Depth varies too much in the region (an edge, a guide or something passing)"
        }
        return DistanceReading(distance_mm: median, spread_mm: spread, mapCount: used, goodMapCount: good,
                               validShare: validShare, isValid: problem == nil, problem: problem)
    }

    /// Millimetres per pixel at the distance: Z ÷ fx, with fx in pixels of the image whose pixels are meant.
    static func mmPerPixel(distance_mm: Double, fx_px: Double) -> Double? {
        guard distance_mm > 0, fx_px > 0 else { return nil }
        return distance_mm / fx_px
    }

    /// Linear-interpolated percentile `p` (0…1) of sorted values (numpy's default).
    static func percentile(_ sorted: [Double], _ p: Double) -> Double {
        guard !sorted.isEmpty else { return 0 }
        let position = p * Double(sorted.count - 1)
        let lower = Int(position.rounded(.down))
        let upper = min(lower + 1, sorted.count - 1)
        let fraction = position - Double(lower)
        return sorted[lower] + (sorted[upper] - sorted[lower]) * fraction
    }
}
