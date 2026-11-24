import Foundation
@preconcurrency import AVFoundation
import UIKit

/// What a probe burst recorded about itself, written next to its data (JSON).
struct BurstSummary: Codable, Equatable {
    var kind: String
    var state: CameraStateRecord
    var exposureUsed_s: Double
    var isoUsed: Double
    var droppedFrames: Int
    var framesWithIntrinsics: Int
    var sensorWidth_px: Int
    var sensorRows: Int
    var roi: NormalizedRect
    var roiPixels: [Int]
    var frameCount: Int
}

struct LightCheckFile: Codable, Equatable {
    var check: LightCheck
    var burst: BurstSummary
}

struct ReadoutFile: Codable, Equatable {
    var lightCheck: LightCheck
    var lightCheckExposure_s: Double
    var test: ReadoutTest
    var bursts: [BurstSummary]
}

/// Settings Diagnostics screen's state and actions (FR-APP-06): every action opens the camera for a few seconds,
/// writes its files into a new folder under `Documents/Diagnostics` and shows a short text.
@MainActor
final class DiagnosticsModel: ObservableObject {
    @Published var shutterDenominator = 2000
    @Published var roiWidthPercent = 50
    @Published var formatIndex = -1
    @Published var sampleFrames = 8
    @Published var tapeMeasureText = ""
    @Published private(set) var isBusy = false
    @Published private(set) var status = ""
    @Published private(set) var resultText = ""
    @Published private(set) var errorText: String?
    @Published private(set) var prompt: String?
    @Published private(set) var cameraDenied = false
    @Published private(set) var zipURL: URL?
    @Published private(set) var storage = (files: 0, bytes: Int64(0))

    static let shutterChoices = [500, 1000, 2000, 4000, 8000]
    static let roiWidthChoices = [25, 50, 75, 100]
    /// Height of the probe's ROI: the readout runs along the rows, so the ROI keeps most of them.
    static let roiHeight = 0.8

    private var turnContinuation: CheckedContinuation<Void, Never>?

    /// Usable formats of the wide camera: (index, text).
    var formatOptions: [(index: Int, text: String)] {
        guard let device = CaptureRig.backDevice(.builtInWideAngleCamera) else { return [] }
        return CaptureRig.usableFormatIndices(of: device).map { ($0, CaptureRig.summary(device.formats[$0])) }
    }

    var roi: NormalizedRect {
        NormalizedRect.centered(width: Double(roiWidthPercent) / 100.0, height: Self.roiHeight)
    }

    private var chosenFormat: Int? { formatIndex >= 0 ? formatIndex : nil }

    func refreshStorage() {
        storage = DiagnosticsStore.summary()
    }

    // MARK: Plumbing

    private func run(_ title: String, _ work: @escaping @MainActor () async throws -> String) {
        guard !isBusy else { return }
        isBusy = true
        errorText = nil
        status = title
        zipURL = nil
        UIApplication.shared.isIdleTimerDisabled = true
        Task {
            if await CameraAccess.request() {
                cameraDenied = false
                do {
                    resultText = try await work()
                } catch {
                    errorText = error.localizedDescription
                }
            } else {
                cameraDenied = true
            }
            isBusy = false
            status = ""
            prompt = nil
            UIApplication.shared.isIdleTimerDisabled = false
            refreshStorage()
        }
    }

    func continueAfterPrompt() {
        prompt = nil
        turnContinuation?.resume()
        turnContinuation = nil
    }

    private func waitForTurn(_ text: String) async {
        prompt = text
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            turnContinuation = continuation
        }
    }

    private func burst(_ request: BurstRequest, label: String) async throws -> BurstResult {
        status = label
        var result = try await DiagnosticsCapture.run(request)
        var attempts = 1
        // A burst of 27 frames with a dropped frame has broken phase steps: repeat it (twice at most).
        while result.droppedFrames > 0 && request.frames == FlickerReadout.burstFrames && attempts < 3 {
            attempts += 1
            status = label + " (again: a frame was dropped)"
            result = try await DiagnosticsCapture.run(request)
        }
        return result
    }

    private func summary(_ kind: String, _ result: BurstResult, roi: NormalizedRect) -> BurstSummary {
        BurstSummary(kind: kind, state: result.state, exposureUsed_s: result.exposureUsed_s, isoUsed: result.isoUsed,
                     droppedFrames: result.droppedFrames, framesWithIntrinsics: result.framesWithIntrinsics,
                     sensorWidth_px: result.sensorWidth_px, sensorRows: result.sensorRows, roi: roi,
                     roiPixels: [result.roiPixels.x0, result.roiPixels.y0, result.roiPixels.x1, result.roiPixels.y1],
                     frameCount: result.frames.count)
    }

    /// Writes `<prefix>frames.csv` and `<prefix>strips.csv` (and the pictures when the burst kept them).
    private func saveBurst(_ result: BurstResult, in folder: URL, prefix: String) throws {
        var rows: [[String]] = [["frame", "timestamp_s", "exposure_s", "iso", "lens_position", "roi_mean",
                                 "fx_px", "fy_px", "cx_px", "cy_px", "gravity_x", "gravity_y", "gravity_z"]]
        for frame in result.frames {
            let k = frame.intrinsics ?? []
            let g = frame.gravity ?? []
            func value(_ array: [Double], _ i: Int, _ decimals: Int) -> String {
                i < array.count ? Num.fixed(array[i], decimals) : ""
            }
            rows.append([String(frame.index), Num.fixed(frame.timestamp_s, 6), Num.fixed(frame.exposure_s, 7),
                         Num.fixed(frame.iso, 1), Num.fixed(frame.lensPosition, 4), Num.fixed(frame.roiMean, 3),
                         value(k, 0, 3), value(k, 1, 3), value(k, 2, 3), value(k, 3, 3),
                         value(g, 0, 4), value(g, 1, 4), value(g, 2, 4)])
        }
        try DiagnosticsStore.write(CSV.make(rows), name: "\(prefix)frames.csv", in: folder)
        var strips: [[String]] = [["frame"] + result.series.centreRows_px.map { "row_" + Num.fixed($0, 1) }]
        for (index, frame) in result.series.means.enumerated() {
            strips.append([String(index)] + frame.map { Num.fixed($0, 4) })
        }
        try DiagnosticsStore.write(CSV.make(strips), name: "\(prefix)strips.csv", in: folder)
        for (index, image) in result.images.enumerated() {
            let name = "\(prefix)frame-" + String(format: "%02d", index) + ".png"
            try DiagnosticsCapture.writePNG(image, to: folder.appendingPathComponent(name))
        }
    }

    private func describe(_ check: LightCheck) -> String {
        var text = "Flicker index \(Num.fixed(check.index, 4)) at \(Num.fixed(check.flickerHz, 0)) Hz "
        text += "(other bins' median \(Num.fixed(check.floorIndex, 4))). "
        if let mains = check.mainsHz {
            text += "Accepted: \(Num.fixed(mains, 0)) Hz mains."
            if check.isAmber { text += " Above 0.03: the quality light would turn amber (Light flickers)." }
        } else {
            text += "Not accepted: no steady flicker found (index below 0.01 or under 3 times the other bins)."
        }
        return text
    }

    private func describe(_ result: BurstResult) -> String {
        var text = "\(result.state.format), \(result.frames.count) frames at \(result.state.fps) fps, "
        text += "exposure \(CameraReport.exposureText(result.exposureUsed_s)), ISO \(Num.fixed(result.isoUsed, 0)), "
        text += "dropped frames \(result.droppedFrames), intrinsics on \(result.framesWithIntrinsics) frames, "
        text += "distortion correction \(result.state.distortionCorrectionEnabled ? "on" : "off")."
        return text
    }

    // MARK: Actions

    func cameraReport() {
        run("Reading the cameras") { [self] in
            let report = CameraReportBuilder.build()
            let folder = try DiagnosticsStore.newFolder(kind: "camera-report")
            try DiagnosticsStore.write(report.text(), name: "camera-report.txt", in: folder)
            try DiagnosticsStore.write(try JSONFile.encode(report), name: "camera-report.json", in: folder)
            return report.text()
        }
    }

    func sampleCapture() {
        run("Capturing sample frames") { [self] in
            let folder = try DiagnosticsStore.newFolder(kind: "samples")
            let request = BurstRequest(formatIndex: chosenFormat, fps: 30, frames: sampleFrames,
                                       exposure: .autoLimited(max_s: 1.0 / Double(shutterDenominator)),
                                       roi: roi, keepImages: true)
            let result = try await burst(request, label: "Capturing \(sampleFrames) frames")
            try saveBurst(result, in: folder, prefix: "")
            try DiagnosticsStore.write(try JSONFile.encode(summary("samples", result, roi: roi)), name: "burst.json", in: folder)
            return "Saved \(result.images.count) pictures of the region. " + describe(result)
        }
    }

    func lightCheck() {
        run("Light check") { [self] in
            let folder = try DiagnosticsStore.newFolder(kind: "light")
            let request = BurstRequest(formatIndex: chosenFormat, fps: 27, frames: FlickerReadout.burstFrames,
                                       exposure: .autoLimited(max_s: 1.0 / Double(shutterDenominator)), roi: roi)
            let result = try await burst(request, label: "Light check: 1 s burst at 1/27 s")
            try saveBurst(result, in: folder, prefix: "")
            guard let check = FlickerReadout.lightCheck(result.series) else {
                throw CaptureError.noFrames("The burst could not be evaluated.")
            }
            let file = LightCheckFile(check: check, burst: summary("light", result, roi: roi))
            try DiagnosticsStore.write(try JSONFile.encode(file), name: "light-check.json", in: folder)
            let text = describe(check) + "\n" + describe(result)
            try DiagnosticsStore.write(text + "\n", name: "light-check.txt", in: folder)
            return text
        }
    }

    func readoutTest() {
        run("Readout test") { [self] in
            let folder = try DiagnosticsStore.newFolder(kind: "readout")
            let lightRequest = BurstRequest(formatIndex: chosenFormat, fps: 27, frames: FlickerReadout.burstFrames,
                                            exposure: .autoLimited(max_s: 1.0 / Double(shutterDenominator)), roi: roi)
            let light = try await burst(lightRequest, label: "Readout test 1 of 4: light check")
            try saveBurst(light, in: folder, prefix: "light-")
            guard let check = FlickerReadout.lightCheck(light.series) else {
                throw CaptureError.noFrames("The light check burst could not be evaluated.")
            }
            let lightSummary = summary("light", light, roi: roi)
            guard check.accepted else {
                let text = describe(check) + "\nThe readout test needs a flickering light. Use the plant light, or the target burst of P0.8."
                try DiagnosticsStore.write(try JSONFile.encode(LightCheckFile(check: check, burst: lightSummary)),
                                           name: "light-check.json", in: folder)
                try DiagnosticsStore.write(text + "\n", name: "readout.txt", in: folder)
                return text
            }
            // Exposure 1/(2F) removes every even harmonic of the light; ISO keeps the brightness of the light check.
            let exposure = 1.0 / (2.0 * check.flickerHz)
            let iso = light.isoUsed * light.exposureUsed_s / exposure
            let format = chosenFormat
            let region = roi
            func readoutRequest() -> BurstRequest {
                BurstRequest(formatIndex: format, fps: 27, frames: FlickerReadout.burstFrames,
                             exposure: .manual(duration_s: exposure, iso: iso), roi: region)
            }
            let first = try await burst(readoutRequest(), label: "Readout test 2 of 4: first burst")
            try saveBurst(first, in: folder, prefix: "burst1-")
            await waitForTurn("Turn the phone 180° about the camera's axis (the lens keeps looking at the same surface), then tap Continue.")
            let second = try await burst(readoutRequest(), label: "Readout test 4 of 4: second burst")
            try saveBurst(second, in: folder, prefix: "burst2-")
            let test = FlickerReadout.readoutTest(lightCheck: check, lightCheckExposure_s: light.exposureUsed_s,
                                                  bursts: [first.series, second.series], sensorRows: light.sensorRows)
            let file = ReadoutFile(lightCheck: check, lightCheckExposure_s: light.exposureUsed_s, test: test,
                                   bursts: [lightSummary, summary("burst1", first, roi: roi), summary("burst2", second, roi: roi)])
            try DiagnosticsStore.write(try JSONFile.encode(file), name: "readout.json", in: folder)
            var text = describe(check) + "\n"
            if let tr = test.readoutTime_s, let direction = test.direction {
                text += "Readout time \(Num.fixed(tr * 1000, 2)) ms, rows read \(direction > 0 ? "top to bottom" : "bottom to top") of the buffer.\n"
            } else {
                text += (test.failure ?? "The test failed.") + "\n"
            }
            for (index, burst) in test.bursts.enumerated() {
                let fit = burst.fit
                text += "Burst \(index + 1): T_r \(fit.map { Num.fixed($0.readoutTime_s * 1000, 2) } ?? "?") ms, "
                text += "amplitude ratio \(burst.amplitudeRatio.map { Num.fixed($0, 3) } ?? "?"), "
                text += "residual \(fit.map { Num.fixed($0.residual_rad, 3) } ?? "?") rad"
                text += burst.failedChecks.isEmpty ? "\n" : ", failed: \(burst.failedChecks.joined(separator: ", "))\n"
            }
            text += "Burst exposure \(CameraReport.exposureText(first.exposureUsed_s)), ISO \(Num.fixed(first.isoUsed, 0)) "
            text += "(wanted ISO \(Num.fixed(iso, 0)); a clamped ISO means the picture may clip)."
            try DiagnosticsStore.write(text + "\n", name: "readout.txt", in: folder)
            return text
        }
    }

    func noiseSeries() {
        run("Noise series") { [self] in
            let folder = try DiagnosticsStore.newFolder(kind: "noise")
            let base = try await burst(BurstRequest(formatIndex: chosenFormat, fps: 30, frames: 2,
                                                    exposure: .autoLimited(max_s: 1.0 / Double(shutterDenominator)),
                                                    roi: roi, keepImages: true), label: "Noise series: finding the light")
            try saveBurst(base, in: folder, prefix: "base-")
            var lines = ["Reference: exposure \(CameraReport.exposureText(base.exposureUsed_s)), ISO \(Num.fixed(base.isoUsed, 0))"]
            var table: [[String]] = [["iso_wanted", "iso_used", "exposure_s", "roi_mean_frame1", "roi_mean_frame2"]]
            for iso in [100.0, 200.0, 400.0, 800.0, 1600.0, 3200.0, 6400.0, 12800.0] {
                let duration = base.exposureUsed_s * base.isoUsed / iso
                let pair = try await burst(BurstRequest(formatIndex: chosenFormat, fps: 30, frames: 2,
                                                        exposure: .manual(duration_s: duration, iso: iso), roi: roi,
                                                        keepImages: true, settle_s: 0.6),
                                           label: "Noise series: ISO \(Int(iso))")
                try saveBurst(pair, in: folder, prefix: "iso\(Int(iso))-")
                let means = pair.frames.map(\.roiMean)
                table.append([Num.fixed(iso, 0), Num.fixed(pair.isoUsed, 0), Num.fixed(pair.exposureUsed_s, 7)]
                             + means.map { Num.fixed($0, 2) })
                lines.append("ISO \(Int(iso)): used \(Num.fixed(pair.isoUsed, 0)), exposure \(CameraReport.exposureText(pair.exposureUsed_s)), mean \(means.map { Num.fixed($0, 1) }.joined(separator: " / "))")
            }
            try DiagnosticsStore.write(CSV.make(table), name: "noise-table.csv", in: folder)
            let text = lines.joined(separator: "\n") + "\nTwo pictures per ISO are saved for the analysis; keep the mat still."
            try DiagnosticsStore.write(text + "\n", name: "noise.txt", in: folder)
            return text
        }
    }

    func lidarProbe() {
        run("LiDAR probe") { [self] in
            let folder = try DiagnosticsStore.newFolder(kind: "lidar")
            let tape = Double(tapeMeasureText.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces))
            let report = try await LidarProbe.run(roi: roi, runFormatIndex: chosenFormat, tape_mm: tape) { [weak self] text in
                Task { @MainActor in self?.status = text }
            }
            try DiagnosticsStore.write(try JSONFile.encode(report), name: "lidar.json", in: folder)
            try DiagnosticsStore.write(report.text(), name: "lidar.txt", in: folder)
            return report.text()
        }
    }

    // MARK: Files

    func prepareZip() {
        do {
            zipURL = try DiagnosticsStore.makeZip()
            errorText = nil
        } catch {
            errorText = error.localizedDescription
        }
    }

    func deleteAll() {
        do {
            try DiagnosticsStore.deleteAll()
            zipURL = nil
            resultText = ""
            errorText = nil
        } catch {
            errorText = error.localizedDescription
        }
        refreshStorage()
    }
}
