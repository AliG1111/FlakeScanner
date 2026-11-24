import Foundation

/// One depth format a video format can deliver (LiDAR camera).
struct DepthFormatInfo: Codable, Equatable, Sendable {
    var width_px: Int
    var height_px: Int
    /// Four-character pixel format code as text, for example "fdep" for `DepthFloat32`.
    var pixelFormat: String
    var minFps: Double?
    var maxFps: Double?
    var isFiltered: Bool?
}

/// One video format of a camera, as plain values (design §3.8, FR-APP-06).
struct FormatInfo: Codable, Equatable, Sendable {
    var width_px: Int
    var height_px: Int
    /// Four-character pixel format code as text, for example "420f".
    var pixelFormat: String
    var minFps: Double
    var maxFps: Double
    var isBinned: Bool
    var supportsVideoHDR: Bool
    var fieldOfView_deg: Double
    var minISO: Double
    var maxISO: Double
    var minExposure_s: Double
    var maxExposure_s: Double
    var maxZoomFactor: Double?
    var depthFormats: [DepthFormatInfo]

    /// "4032×3024 420f 1–60 fps".
    var summary: String {
        let rate = minFps == maxFps ? Num.fixed(maxFps, 0) : "\(Num.fixed(minFps, 0))–\(Num.fixed(maxFps, 0))"
        return "\(width_px)×\(height_px) \(pixelFormat) \(rate) fps"
    }
}

/// One physical camera with its formats and device-wide capabilities.
struct CameraInfo: Codable, Equatable, Sendable {
    var name: String
    var deviceType: String
    var position: String
    var supportsDistortionCorrection: Bool
    var distortionCorrectionEnabled: Bool
    var supportsLowLightBoost: Bool
    var minFocusDistance_mm: Int?
    var supportsLockedLensPosition: Bool
    var supportsCustomExposure: Bool
    var formats: [FormatInfo]
    /// Properties of the chosen active format and its connection, after a test configuration (nil when not tested).
    var intrinsicsDeliverySupported: Bool?
    var activeFormatSummary: String?
}

/// Device and system facts of a report.
struct DeviceInfo: Codable, Equatable, Sendable {
    var model: String
    var systemVersion: String
    var appVersion: String
    var date: String
}

/// The camera report (FR-APP-06 a): written as text and JSON into the diagnostics zip.
struct CameraReport: Codable, Equatable, Sendable {
    var device: DeviceInfo
    var cameras: [CameraInfo]

    /// Human-readable text.
    func text() -> String {
        var lines: [String] = []
        lines.append("Flake Scanner camera report")
        lines.append("\(device.model), \(device.systemVersion), \(device.appVersion), \(device.date)")
        for camera in cameras {
            lines.append("")
            lines.append("== \(camera.name) (\(camera.deviceType), \(camera.position))")
            lines.append("distortion correction: supported \(yesNo(camera.supportsDistortionCorrection)), "
                         + "enabled \(yesNo(camera.distortionCorrectionEnabled)); low-light boost supported "
                         + "\(yesNo(camera.supportsLowLightBoost))")
            lines.append("custom exposure \(yesNo(camera.supportsCustomExposure)); locked lens position "
                         + "\(yesNo(camera.supportsLockedLensPosition)); closest focus "
                         + (camera.minFocusDistance_mm.map { "\($0) mm" } ?? "unknown"))
            if let delivered = camera.intrinsicsDeliverySupported {
                lines.append("intrinsics delivery on \(camera.activeFormatSummary ?? "the active format"): \(yesNo(delivered))")
            }
            for format in camera.formats {
                var line = "  \(format.summary)\(format.isBinned ? " binned" : "")"
                line += ", FOV \(Num.fixed(format.fieldOfView_deg, 1))°"
                line += ", ISO \(Num.fixed(format.minISO, 0))–\(Num.fixed(format.maxISO, 0))"
                line += ", exposure \(Self.exposureText(format.minExposure_s))–\(Self.exposureText(format.maxExposure_s))"
                if format.supportsVideoHDR { line += ", video HDR" }
                lines.append(line)
                for depth in format.depthFormats {
                    let rate = depth.maxFps.map { ", up to \(Num.fixed($0, 0)) fps" } ?? ""
                    let filtered = depth.isFiltered.map { ", filtered \(yesNo($0))" } ?? ""
                    lines.append("    depth \(depth.width_px)×\(depth.height_px) \(depth.pixelFormat)\(rate)\(filtered)")
                }
            }
        }
        return lines.joined(separator: "\n") + "\n"
    }

    /// "1/4000 s" for short exposures, "0.5 s" for long ones.
    static func exposureText(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds > 0 else { return "?" }
        return seconds >= 0.5 ? "\(Num.fixed(seconds, 2)) s" : "1/\(Int((1.0 / seconds).rounded())) s"
    }

    private func yesNo(_ value: Bool) -> String { value ? "yes" : "no" }
}

/// Everything the LiDAR probe measures (FR-APP-06 c, design §6.17), as plain values.
struct LidarReport: Codable, Equatable, Sendable {
    /// A format of the LiDAR camera with depth delivery and which controls it accepted.
    struct FormatCheck: Codable, Equatable, Sendable {
        var format: String
        var depthFormat: String?
        var acceptsCustomExposure: Bool
        var acceptsLockedFocus: Bool
        var acceptsFixedFrameDuration: Bool
        /// Frames (video plus depth) arrived with the three controls applied, and at what rate.
        var framesDelivered: Int
        var deliveredFps: Double?
        var note: String?
    }

    /// The camera state recorded before the switch and the state after switching back and locking.
    struct CameraState: Codable, Equatable, Sendable {
        var exposure_s: Double
        var iso: Double
        var lensPosition: Double
        var whiteBalanceGains: [Double]
    }

    struct Zone: Codable, Equatable, Sendable {
        var name: String
        var reading: DistanceReading
    }

    var formatChecks: [FormatCheck]
    /// Time from starting the LiDAR camera until the first video-and-depth pair, s.
    var timeToFirstDepth_s: Double?
    /// Time until exposure and ISO stopped changing on the LiDAR camera, s.
    var settleOnLidar_s: Double?
    /// Time from starting the run's camera again until its first frame, s.
    var timeBackToFirstFrame_s: Double?
    var stateBefore: CameraState?
    var stateAfterSwitch: CameraState?
    var stateAfterLock: CameraState?
    /// Distance readings: the ROI, and the centre and the four corners of the depth map.
    var zones: [Zone]
    var depthMapSize: String?
    var tapeMeasure_mm: Double?
    var notes: [String]

    func text() -> String {
        var lines: [String] = ["Flake Scanner LiDAR probe"]
        for check in formatChecks {
            lines.append("")
            lines.append("format \(check.format)" + (check.depthFormat.map { ", depth \($0)" } ?? ""))
            lines.append("  custom exposure \(yn(check.acceptsCustomExposure)), locked focus \(yn(check.acceptsLockedFocus)), "
                         + "fixed frame duration \(yn(check.acceptsFixedFrameDuration)); \(check.framesDelivered) frames"
                         + (check.deliveredFps.map { " at \(Num.fixed($0, 1)) fps" } ?? ""))
            if let note = check.note { lines.append("  \(note)") }
        }
        lines.append("")
        lines.append("time to first depth: \(seconds(timeToFirstDepth_s)); settled on the LiDAR camera after "
                     + "\(seconds(settleOnLidar_s)); back to the run's camera: first frame after \(seconds(timeBackToFirstFrame_s))")
        for (label, state) in [("before the switch", stateBefore), ("after the switch", stateAfterSwitch),
                               ("after the locks", stateAfterLock)] {
            guard let state else { continue }
            let gains = state.whiteBalanceGains.map { Num.fixed($0, 3) }.joined(separator: " / ")
            lines.append("state \(label): exposure \(CameraReport.exposureText(state.exposure_s)), ISO \(Num.fixed(state.iso, 0)), "
                         + "lens \(Num.fixed(state.lensPosition, 3)), white balance gains \(gains)")
        }
        if let size = depthMapSize { lines.append("depth map \(size)") }
        for zone in zones {
            let r = zone.reading
            if let z = r.distance_mm, let s = r.spread_mm {
                lines.append("\(zone.name): \(Num.fixed(z, 0)) mm, spread \(Num.fixed(s, 1)) mm, valid \(Num.fixed(r.validShare * 100, 0)) %"
                             + (r.isValid ? "" : " (not valid: \(r.problem ?? "?"))"))
            } else {
                lines.append("\(zone.name): no reading (\(r.problem ?? "?"))")
            }
        }
        if let tape = tapeMeasure_mm { lines.append("tape measure: \(Num.fixed(tape, 0)) mm") }
        for note in notes { lines.append(note) }
        return lines.joined(separator: "\n") + "\n"
    }

    private func yn(_ value: Bool) -> String { value ? "yes" : "no" }

    private func seconds(_ value: Double?) -> String {
        value.map { "\(Num.fixed($0, 2)) s" } ?? "n/a"
    }
}
