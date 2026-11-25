import Foundation

/// A rectangle in buffer coordinates as fractions of the frame (0…1, origin at the top-left of the sensor buffer,
/// x along the buffer's rows, y down). Design §6.1: the ROI is a `NormalizedRect` in buffer coordinates.
struct NormalizedRect: Codable, Equatable, Sendable {
    var x: Double
    var y: Double
    var width: Double
    var height: Double

    /// The whole frame.
    static let full = NormalizedRect(x: 0, y: 0, width: 1, height: 1)

    /// A rectangle of the given size centred in the frame, for example `centered(width: 0.5, height: 0.8)`.
    static func centered(width: Double, height: Double) -> NormalizedRect {
        NormalizedRect(x: (1 - width) / 2, y: (1 - height) / 2, width: width, height: height)
    }

    /// The same rectangle cut to the frame (never negative, never beyond 1).
    func clamped() -> NormalizedRect {
        let x0 = min(max(x, 0), 1)
        let y0 = min(max(y, 0), 1)
        let x1 = min(max(x + width, 0), 1)
        let y1 = min(max(y + height, 0), 1)
        return NormalizedRect(x: x0, y: y0, width: max(0, x1 - x0), height: max(0, y1 - y0))
    }

    /// Whole-pixel rectangle `[x0, x1) × [y0, y1)` in a frame of `width_px` × `height_px`: edges are rounded to the
    /// nearest pixel, and the result is at least one pixel wide and high and inside the frame. `nil` for an empty
    /// rectangle or a frame without pixels.
    func pixelBounds(width_px: Int, height_px: Int) -> (x0: Int, y0: Int, x1: Int, y1: Int)? {
        guard width_px > 0, height_px > 0 else { return nil }
        let c = clamped()
        guard c.width > 0, c.height > 0 else { return nil }
        var x0 = Int((c.x * Double(width_px)).rounded())
        var y0 = Int((c.y * Double(height_px)).rounded())
        var x1 = Int(((c.x + c.width) * Double(width_px)).rounded())
        var y1 = Int(((c.y + c.height) * Double(height_px)).rounded())
        x0 = min(max(x0, 0), width_px - 1)
        y0 = min(max(y0, 0), height_px - 1)
        x1 = min(max(x1, x0 + 1), width_px)
        y1 = min(max(y1, y0 + 1), height_px)
        return (x0, y0, x1, y1)
    }
}
