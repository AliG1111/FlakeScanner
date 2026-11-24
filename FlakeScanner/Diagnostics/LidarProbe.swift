import Foundation
import AVFoundation

/// Time from the first call of `mark()` to the first `frame()`: how long a camera took to deliver after it started.
private final class FirstFrameTimer: @unchecked Sendable {
    private let lock = NSLock()
    private var start = 0.0
    private var first: Double?

    func mark() {
        lock.lock(); defer { lock.unlock() }
        start = ProcessInfo.processInfo.systemUptime
        first = nil
    }

    func frame() {
        lock.lock(); defer { lock.unlock() }
        if first == nil { first = ProcessInfo.processInfo.systemUptime }
    }

    var elapsed_s: Double? {
        lock.lock(); defer { lock.unlock() }
        return first.map { $0 - start }
    }
}

/// The LiDAR probe (FR-APP-06 c, design §6.17, P0.7): the camera switch of the distance reading as Start would do it,
/// what the LiDAR camera accepts, and the distance at the ROI, the centre and the corners.
enum LidarProbe {
    /// Runs the probe with the run's camera (the wide camera) in `runFormatIndex` (nil: the default) at 30 fps.
    /// `progress` gets a short text for each step.
    static func run(roi: NormalizedRect, runFormatIndex: Int?, tape_mm: Double?,
                    progress: @escaping @Sendable (String) -> Void) async throws -> LidarReport {
        guard LidarDistance.isSupported, let lidarDevice = AVCaptureDevice.default(.builtInLiDARDepthCamera, for: .video, position: .back) else {
            throw CaptureError.noCamera("This iPhone has no LiDAR camera.")
        }
        guard let wide = CaptureRig.backDevice(.builtInWideCamera) else {
            throw CaptureError.noCamera("This iPhone has no wide camera.")
        }
        var notes: [String] = []

        // 1. The run's camera settles on the light and its state is recorded (what Start records before the switch).
        progress("Run camera: settling on the light")
        let before = try await openRunCamera(wide, formatIndex: runFormatIndex, settle: true, timer: nil)
        let recordedState = before.state
        let recorded = LidarReport.CameraState(exposure_s: recordedState.exposure_s, iso: recordedState.iso,
                                               lensPosition: recordedState.lensPosition,
                                               whiteBalanceGains: recordedState.whiteBalanceGains)
        await before.rig.close()
        let runSize = frameSize(of: wide, formatIndex: runFormatIndex)

        // 2. The LiDAR camera replaces it: time to the first pair, the settle time, the controls it accepts.
        progress("LiDAR camera: collecting depth maps")
        let indices = LidarDistance.depthFormatIndices(of: lidarDevice)
        guard let best = indices.first else {
            throw CaptureError.configuration("The LiDAR camera has no format with depth delivery.")
        }
        let main = try await LidarDistance().collect(.init(formatIndex: best, maxMaps: 30, timeout_s: 8, applyControls: true))
        let switched = main.state
        var checks: [LidarReport.FormatCheck] = [formatCheck(main, index: best, device: lidarDevice)]

        // 3. Other depth formats, tried the same way for a moment.
        for index in indices.dropFirst().prefix(2) {
            progress("LiDAR camera: another format")
            do {
                let other = try await LidarDistance().collect(.init(formatIndex: index, maxMaps: 15, timeout_s: 5, applyControls: true))
                checks.append(formatCheck(other, index: index, device: lidarDevice))
            } catch {
                let failed = LidarReport.FormatCheck(format: CaptureRig.summary(lidarDevice.formats[index]), depthFormat: nil,
                                                     acceptsCustomExposure: false, acceptsLockedFocus: false,
                                                     acceptsFixedFrameDuration: false, framesDelivered: 0, deliveredFps: nil,
                                                     note: error.localizedDescription)
                checks.append(failed)
            }
        }

        // 4. Back to the run's camera: time to its first frame, then the recorded values are locked as Start would.
        progress("Run camera: back from the LiDAR camera")
        let timer = FirstFrameTimer()
        let back = try await openRunCamera(wide, formatIndex: runFormatIndex, settle: false, timer: timer)
        let afterSwitch = back.rig.state()
        _ = try? await back.rig.lockExposure(duration_s: recorded.exposure_s, iso: recorded.iso)
        await back.rig.lockFocusAndWhiteBalance(lensPosition: recorded.lensPosition, gains: recorded.whiteBalanceGains)
        try await Task.sleep(nanoseconds: 600_000_000)
        let locked = back.rig.state()
        await back.rig.close()

        // 5. Distances.
        var zones: [LidarReport.Zone] = []
        if let depthK = main.depthIntrinsics, let videoK = main.videoIntrinsics {
            if let footprint = CameraScale.footprint(roi: roi, video: videoK, videoSize_px: main.videoSize_px,
                                                     depth: depthK, depthSize_px: main.depthSize_px) {
                zones.append(LidarReport.Zone(name: "ROI", reading: CameraScale.reading(maps: main.maps, footprint: footprint)))
            }
            if let z = zones.first?.reading.distance_mm {
                let fxLidar = videoK.fx_px
                if let mm = CameraScale.mmPerPixel(distance_mm: z, fx_px: fxLidar) {
                    notes.append("mm per px at the ROI distance in the LiDAR camera's \(main.videoSize_px.width) px wide frames: \(Num.fixed(mm, 4))")
                }
                if let runSize, main.videoSize_px.width > 0 {
                    let fxRun = fxLidar * Double(runSize.width) / Double(main.videoSize_px.width)
                    if let mm = CameraScale.mmPerPixel(distance_mm: z, fx_px: fxRun) {
                        notes.append("mm per px in the run format's \(runSize.width) px wide frames (assuming the same field of view): \(Num.fixed(mm, 4))")
                    }
                }
            }
        } else {
            notes.append("The frames carried no intrinsics, so the ROI could not be mapped into the depth map.")
        }
        for zone in ProbeMath.lidarZones(width: main.depthSize_px.width, height: main.depthSize_px.height) {
            zones.append(LidarReport.Zone(name: zone.name, reading: CameraScale.reading(maps: main.maps, footprint: zone.footprint)))
        }
        notes.append("Depth filtering was \(main.depthIsFiltered ? "ON (unexpected)" : "off"); \(main.pairs) video and depth pairs.")
        if let after = back.firstFrameNote(timer: timer) { notes.append(after) }

        func state(_ s: CameraStateRecord?) -> LidarReport.CameraState? {
            s.map { LidarReport.CameraState(exposure_s: $0.exposure_s, iso: $0.iso, lensPosition: $0.lensPosition,
                                            whiteBalanceGains: $0.whiteBalanceGains) }
        }
        return LidarReport(
            formatChecks: checks,
            timeToFirstDepth_s: main.timeToFirstPair_s,
            settleOnLidar_s: ProbeMath.settleTime(main.settleSamples),
            timeBackToFirstFrame_s: timer.elapsed_s,
            stateBefore: recorded,
            stateAfterSwitch: state(switched) ?? state(afterSwitch),
            stateAfterLock: state(locked),
            zones: zones,
            depthMapSize: "\(main.depthSize_px.width)×\(main.depthSize_px.height)",
            tapeMeasure_mm: tape_mm,
            notes: notes)
    }

    private static func formatCheck(_ capture: LidarCapture, index: Int, device: AVCaptureDevice) -> LidarReport.FormatCheck {
        var note: String?
        if !capture.acceptsCustomExposure || !capture.acceptsLockedFocus || !capture.acceptsFixedFrameDuration {
            note = "Not every control was accepted: the run's camera cannot be this one with those controls."
        }
        return LidarReport.FormatCheck(format: capture.formatSummary, depthFormat: capture.depthSummary,
                                       acceptsCustomExposure: capture.acceptsCustomExposure,
                                       acceptsLockedFocus: capture.acceptsLockedFocus,
                                       acceptsFixedFrameDuration: capture.acceptsFixedFrameDuration,
                                       framesDelivered: capture.pairs, deliveredFps: capture.deliveredFps, note: note)
    }

    private static func frameSize(of device: AVCaptureDevice, formatIndex: Int?) -> (width: Int, height: Int)? {
        guard let index = formatIndex ?? CaptureRig.defaultFormatIndex(of: device), device.formats.indices.contains(index) else {
            return nil
        }
        return CaptureRig.dimensions(device.formats[index])
    }

    /// The run's camera opened as the probe's run: returned with its rig so that the caller closes it.
    private struct RunCamera {
        var rig: CaptureRig
        var state: CameraStateRecord

        func firstFrameNote(timer: FirstFrameTimer) -> String? {
            timer.elapsed_s == nil ? "The run's camera delivered no frame after the switch back." : nil
        }
    }

    private static func openRunCamera(_ device: AVCaptureDevice, formatIndex: Int?, settle: Bool,
                                      timer: FirstFrameTimer?) async throws -> RunCamera {
        let rig = CaptureRig(device: device)
        if let timer { rig.onFrame = { _ in timer.frame() } }
        timer?.mark()
        _ = try await rig.open(formatIndex: formatIndex, fps: 30)
        if settle {
            try await rig.setAutoExposure(maxDuration_s: 1.0 / 1000.0)
            await rig.waitForExposureToSettle(minimum_s: 1.5, timeout_s: 5)
        } else if let timer {
            // Wait for the first frame (at most 3 s) so the time is measured.
            let deadline = Date().addingTimeInterval(3)
            while timer.elapsed_s == nil && Date() < deadline {
                try await Task.sleep(nanoseconds: 10_000_000)
            }
        }
        return RunCamera(rig: rig, state: rig.state())
    }
}
