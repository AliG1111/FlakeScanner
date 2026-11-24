import Foundation
import AVFoundation
import CoreMedia
import simd

/// Problems of the probe and of the capture code, worded for the person at the line.
enum CaptureError: LocalizedError {
    case noCamera(String)
    case configuration(String)
    case noFrames(String)

    var errorDescription: String? {
        switch self {
        case .noCamera(let text), .configuration(let text), .noFrames(let text): return text
        }
    }
}

/// The camera state in use, as plain values (recorded with every probe result).
struct CameraStateRecord: Codable, Equatable, Sendable {
    var deviceType: String
    var format: String
    var isBinned: Bool
    var fps: Int
    var distortionCorrectionSupported: Bool
    var distortionCorrectionEnabled: Bool
    var videoHDREnabled: Bool
    var stabilizationMode: String
    var intrinsicsDeliverySupported: Bool
    var exposure_s: Double
    var iso: Double
    var lensPosition: Double
    var whiteBalanceGains: [Double]
    var focusMode: String
    var exposureMode: String
    var systemPressure: String
}

/// One back camera in an `AVCaptureSession` with the fixed image processing of design §6.10 (stabilization off, video
/// HDR off, low-light boost off, distortion correction on, intrinsics delivery on, sensor orientation), a chosen format
/// and fixed frame duration, and the exposure, focus and white-balance controls. Frames go to `onFrame` on the data
/// queue. Session changes happen on the session queue (`flakescanner.capture.session`), frames on
/// `flakescanner.capture.data`.
///
/// Device only: the simulator has no camera.
final class CaptureRig: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate, @unchecked Sendable {
    let device: AVCaptureDevice
    let session = AVCaptureSession()
    /// Called for every frame on the data queue; set before `start`.
    var onFrame: (@Sendable (CMSampleBuffer) -> Void)?

    private let sessionQueue = DispatchQueue(label: "flakescanner.capture.session")
    private let dataQueue = DispatchQueue(label: "flakescanner.capture.data", qos: .userInitiated)
    private let output = AVCaptureVideoDataOutput()
    private var fps = 30
    private var intrinsicsSupported = false
    private var stabilization = "unknown"

    init(device: AVCaptureDevice) {
        self.device = device
        super.init()
    }

    static func backDevice(_ type: AVCaptureDevice.DeviceType) -> AVCaptureDevice? {
        AVCaptureDevice.default(type, for: .video, position: .back)
    }

    static let eightBitFullRange = kCVPixelFormatType_420YpCbCr8BiPlanarFullRange

    static func dimensions(_ format: AVCaptureDevice.Format) -> (width: Int, height: Int) {
        let d = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
        return (Int(d.width), Int(d.height))
    }

    static func fourCC(_ code: FourCharCode) -> String {
        let bytes = [UInt8((code >> 24) & 0xff), UInt8((code >> 16) & 0xff), UInt8((code >> 8) & 0xff), UInt8(code & 0xff)]
        let text = String(bytes: bytes, encoding: .ascii) ?? "????"
        return text.unicodeScalars.allSatisfy { $0.value >= 32 && $0.value < 127 } ? text : "0x" + String(code, radix: 16)
    }

    static func summary(_ format: AVCaptureDevice.Format) -> String {
        let size = dimensions(format)
        let rates = format.videoSupportedFrameRateRanges
        let low = rates.map(\.minFrameRate).min() ?? 0
        let high = rates.map(\.maxFrameRate).max() ?? 0
        let code = fourCC(CMFormatDescriptionGetMediaSubType(format.formatDescription))
        return "\(size.width)×\(size.height) \(code) \(Num.fixed(low, 0))–\(Num.fixed(high, 0)) fps"
            + (format.isVideoBinned ? " binned" : "")
    }

    /// Formats the probe can use: 420f (8-bit, full range) and at least 30 fps.
    static func usableFormatIndices(of device: AVCaptureDevice) -> [Int] {
        device.formats.indices.filter { index in
            let format = device.formats[index]
            return CMFormatDescriptionGetMediaSubType(format.formatDescription) == eightBitFullRange
                && format.videoSupportedFrameRateRanges.contains { $0.maxFrameRate >= 30 }
        }
    }

    /// Default format: the most pixels, not binned before binned, then the highest frame rate (design §6.10).
    static func defaultFormatIndex(of device: AVCaptureDevice) -> Int? {
        func key(_ index: Int) -> (Int, Int, Double) {
            let format = device.formats[index]
            let size = dimensions(format)
            let rate = format.videoSupportedFrameRateRanges.map(\.maxFrameRate).max() ?? 0
            return (size.width * size.height, format.isVideoBinned ? 0 : 1, rate)
        }
        return usableFormatIndices(of: device).max { key($0) < key($1) }
    }

    /// fx, fy, cx, cy in pixels of the frame from the intrinsic matrix attached to a frame (when delivery is on).
    static func intrinsics(of sampleBuffer: CMSampleBuffer) -> [Double]? {
        guard let attachment = CMGetAttachment(sampleBuffer, key: kCMSampleBufferAttachmentKey_CameraIntrinsicMatrix,
                                               attachmentModeOut: nil),
              let data = attachment as? Data, data.count == MemoryLayout<matrix_float3x3>.size else { return nil }
        var matrix = matrix_float3x3()
        withUnsafeMutableBytes(of: &matrix) { raw in _ = data.copyBytes(to: raw) }
        return [Double(matrix.columns.0.x), Double(matrix.columns.1.y), Double(matrix.columns.2.x), Double(matrix.columns.2.y)]
    }

    // MARK: Session queue helper

    private func onSession<T: Sendable>(_ work: @escaping @Sendable () throws -> T) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            sessionQueue.async {
                do { continuation.resume(returning: try work()) } catch { continuation.resume(throwing: error) }
            }
        }
    }

    // MARK: Configuration and start / stop

    /// Opens the camera with the fixed processing, the format (nil: the default) and the frame rate, and starts it.
    /// Returns the applied state.
    func open(formatIndex: Int?, fps: Int) async throws -> CameraStateRecord {
        try await onSession { [self] in
            try configure(formatIndex: formatIndex, fps: fps)
            session.startRunning()
            guard session.isRunning else { throw CaptureError.configuration("The camera did not start.") }
            return state()
        }
    }

    func close() async {
        _ = try? await onSession { [self] in
            if session.isRunning { session.stopRunning() }
            output.setSampleBufferDelegate(nil, queue: nil)
            for input in session.inputs { session.removeInput(input) }
            for existing in session.outputs { session.removeOutput(existing) }
        }
    }

    private func configure(formatIndex: Int?, fps: Int) throws {
        guard fps > 0 else { throw CaptureError.configuration("The frame rate must be positive.") }
        guard let index = formatIndex ?? CaptureRig.defaultFormatIndex(of: device), device.formats.indices.contains(index) else {
            throw CaptureError.configuration("This camera has no usable video format.")
        }
        let format = device.formats[index]
        guard format.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= Double(fps) && Double(fps) <= $0.maxFrameRate }) else {
            throw CaptureError.configuration("This format cannot run at \(fps) frames per second.")
        }
        self.fps = fps

        session.beginConfiguration()
        let input = try AVCaptureDeviceInput(device: device)
        guard session.canAddInput(input) else {
            session.commitConfiguration()
            throw CaptureError.configuration("Cannot open the camera.")
        }
        session.addInput(input)
        output.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: CaptureRig.eightBitFullRange]
        output.alwaysDiscardsLateVideoFrames = true
        output.setSampleBufferDelegate(self, queue: dataQueue)
        guard session.canAddOutput(output) else {
            session.commitConfiguration()
            throw CaptureError.configuration("Cannot read video frames.")
        }
        session.addOutput(output)
        session.commitConfiguration()

        try device.lockForConfiguration()
        defer { device.unlockForConfiguration() }
        device.activeFormat = format
        let duration = CMTime(value: 1, timescale: CMTimeScale(fps))
        device.activeVideoMinFrameDuration = duration
        device.activeVideoMaxFrameDuration = duration
        if format.isVideoHDRSupported {
            device.automaticallyAdjustsVideoHDREnabled = false
            device.isVideoHDREnabled = false
        }
        if device.isLowLightBoostSupported {
            device.automaticallyEnablesLowLightBoostWhenAvailable = false
        }
        if device.isGeometricDistortionCorrectionSupported {
            device.isGeometricDistortionCorrectionEnabled = true
        }
        if device.isFocusModeSupported(.continuousAutoFocus) {
            device.focusMode = .continuousAutoFocus
        }
        if device.isExposureModeSupported(.continuousAutoExposure) {
            device.exposureMode = .continuousAutoExposure
        }
        if let connection = output.connection(with: .video) {
            if connection.isVideoRotationAngleSupported(0) { connection.videoRotationAngle = 0 }
            if connection.isVideoStabilizationSupported {
                connection.preferredVideoStabilizationMode = .off
                stabilization = "off requested"
            } else {
                stabilization = "not supported"
            }
            intrinsicsSupported = connection.isCameraIntrinsicMatrixDeliverySupported
            if intrinsicsSupported { connection.isCameraIntrinsicMatrixDeliveryEnabled = true }
        }
    }

    // MARK: State

    func gains() -> [Double] {
        let g = device.deviceWhiteBalanceGains
        return [Double(g.redGain), Double(g.greenGain), Double(g.blueGain)]
    }

    func state() -> CameraStateRecord {
        let format = device.activeFormat
        let focus: String
        switch device.focusMode {
        case .locked: focus = "locked"
        case .autoFocus: focus = "auto"
        case .continuousAutoFocus: focus = "continuous"
        @unknown default: focus = "unknown"
        }
        let exposure: String
        switch device.exposureMode {
        case .locked: exposure = "locked"
        case .autoExpose: exposure = "auto"
        case .continuousAutoExposure: exposure = "continuous"
        case .custom: exposure = "custom"
        @unknown default: exposure = "unknown"
        }
        let pressure: String
        switch device.systemPressureState.level {
        case .nominal: pressure = "nominal"
        case .fair: pressure = "fair"
        case .serious: pressure = "serious"
        case .critical: pressure = "critical"
        case .shutdown: pressure = "shutdown"
        default: pressure = "unknown"
        }
        return CameraStateRecord(
            deviceType: device.deviceType.rawValue,
            format: CaptureRig.summary(format),
            isBinned: format.isVideoBinned,
            fps: fps,
            distortionCorrectionSupported: device.isGeometricDistortionCorrectionSupported,
            distortionCorrectionEnabled: device.isGeometricDistortionCorrectionEnabled,
            videoHDREnabled: device.isVideoHDREnabled,
            stabilizationMode: stabilization,
            intrinsicsDeliverySupported: intrinsicsSupported,
            exposure_s: device.exposureDuration.seconds,
            iso: Double(device.iso),
            lensPosition: Double(device.lensPosition),
            whiteBalanceGains: gains(),
            focusMode: focus,
            exposureMode: exposure,
            systemPressure: pressure)
    }

    // MARK: Exposure, focus and white balance

    /// Longest and shortest exposure the active format and the frame duration allow, seconds.
    func exposureRange_s() -> (min: Double, max: Double) {
        let format = device.activeFormat
        return (max(format.minExposureDuration.seconds, 1e-6),
                min(format.maxExposureDuration.seconds, 1.0 / Double(fps)))
    }

    func isoRange() -> (min: Double, max: Double) {
        (Double(device.activeFormat.minISO), Double(device.activeFormat.maxISO))
    }

    /// Automatic exposure with the exposure limited to `max_s` (clamped to the format), as at Start before the lock.
    func setAutoExposure(maxDuration_s: Double) async throws {
        let range = exposureRange_s()
        let limit = min(max(maxDuration_s, range.min), range.max)
        try await onSession { [self] in
            try device.lockForConfiguration()
            defer { device.unlockForConfiguration() }
            if device.isExposureModeSupported(.continuousAutoExposure) { device.exposureMode = .continuousAutoExposure }
            device.activeMaxExposureDuration = CMTime(seconds: limit, preferredTimescale: 1_000_000)
        }
    }

    /// Waits until the automatic exposure has settled (at least `minimum_s`, at most `timeout_s`).
    func waitForExposureToSettle(minimum_s: Double, timeout_s: Double) async {
        let start = Date()
        while true {
            let elapsed = Date().timeIntervalSince(start)
            if elapsed >= timeout_s { return }
            if elapsed >= minimum_s && !device.isAdjustingExposure { return }
            try? await Task.sleep(nanoseconds: 50_000_000)
        }
    }

    /// Custom exposure at `duration_s` and `iso`, both clamped to the format. Returns the values applied.
    func lockExposure(duration_s: Double, iso: Double) async throws -> (duration_s: Double, iso: Double) {
        let range = exposureRange_s()
        let isoLimits = isoRange()
        let duration = min(max(duration_s, range.min), range.max)
        let isoValue = min(max(iso, isoLimits.min), isoLimits.max)
        guard device.isExposureModeSupported(.custom) else {
            throw CaptureError.configuration("This camera does not support a fixed exposure.")
        }
        try await onSession { [self] in
            try device.lockForConfiguration()
            device.activeMaxExposureDuration = CMTime(seconds: range.max, preferredTimescale: 1_000_000)
            device.unlockForConfiguration()
        }
        await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
            sessionQueue.async { [self] in
                do {
                    try device.lockForConfiguration()
                } catch {
                    continuation.resume()
                    return
                }
                device.setExposureModeCustom(duration: CMTime(seconds: duration, preferredTimescale: 1_000_000),
                                             iso: Float(isoValue)) { _ in continuation.resume() }
                device.unlockForConfiguration()
            }
        }
        return (duration, isoValue)
    }

    /// Locks the lens at `lensPosition` and the white balance at `gains` (nil: as they are now).
    func lockFocusAndWhiteBalance(lensPosition: Double?, gains target: [Double]?) async {
        let lens = Float(lensPosition ?? Double(device.lensPosition))
        let maxGain = device.maxWhiteBalanceGain
        let current = device.deviceWhiteBalanceGains
        var wanted = current
        if let target, target.count == 3 {
            wanted = AVCaptureDevice.WhiteBalanceGains(redGain: min(max(Float(target[0]), 1), maxGain),
                                                       greenGain: min(max(Float(target[1]), 1), maxGain),
                                                       blueGain: min(max(Float(target[2]), 1), maxGain))
        }
        if device.isLockingFocusWithCustomLensPositionSupported {
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                sessionQueue.async { [self] in
                    do { try device.lockForConfiguration() } catch { continuation.resume(); return }
                    device.setFocusModeLocked(lensPosition: lens) { _ in continuation.resume() }
                    device.unlockForConfiguration()
                }
            }
        }
        if device.isWhiteBalanceModeSupported(.locked) {
            await withCheckedContinuation { (continuation: CheckedContinuation<Void, Never>) in
                sessionQueue.async { [self] in
                    do { try device.lockForConfiguration() } catch { continuation.resume(); return }
                    device.setWhiteBalanceModeLocked(with: wanted) { _ in continuation.resume() }
                    device.unlockForConfiguration()
                }
            }
        }
    }

    // MARK: AVCaptureVideoDataOutputSampleBufferDelegate

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        onFrame?(sampleBuffer)
    }
}
