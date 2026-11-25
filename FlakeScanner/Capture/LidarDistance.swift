import Foundation
@preconcurrency import AVFoundation
import CoreMedia
import simd

/// What one collection of LiDAR depth maps delivered.
struct LidarCapture: Sendable {
    var maps: [DepthMap]
    var depthIntrinsics: PinholeIntrinsics?
    /// Intrinsics of the video frames of the LiDAR camera (fx, fy, cx, cy in their pixels) and the frame size.
    var videoIntrinsics: PinholeIntrinsics?
    var videoSize_px: (width: Int, height: Int)
    var depthSize_px: (width: Int, height: Int)
    var formatSummary: String
    var depthSummary: String
    var depthIsFiltered: Bool
    /// Time from starting the session until the first video-and-depth pair, s.
    var timeToFirstPair_s: Double
    /// Exposure and ISO of every pair (device values) for the settle time.
    var settleSamples: [ProbeMath.SettleSample]
    var deliveredFps: Double?
    var pairs: Int
    /// Which of the run's controls the LiDAR camera accepted (only when asked for).
    var acceptsCustomExposure = false
    var acceptsLockedFocus = false
    var acceptsFixedFrameDuration = false
    var state: CameraStateRecord?
}

/// The LiDAR depth camera for the distance reading (design §6.17): a video format with depth delivery, unfiltered
/// `DepthFloat32` maps paired with the video frames by `AVCaptureDataOutputSynchronizer` (Phone LiDAR's Line scan setup).
/// Session changes on the session queue, maps on the data queue. Device only.
final class LidarDistance: NSObject, AVCaptureDataOutputSynchronizerDelegate, @unchecked Sendable {
    static var isSupported: Bool {
        AVCaptureDevice.default(.builtInLiDARDepthCamera, for: .video, position: .back) != nil
    }

    struct Options: Sendable {
        /// Index into the LiDAR camera's formats; nil takes the best-scoring one.
        var formatIndex: Int?
        var maxMaps = 30
        var timeout_s = 8.0
        /// Try the run's controls (custom exposure, locked focus, fixed 30 fps frame duration) while collecting.
        var applyControls = false
    }

    private let sessionQueue = DispatchQueue(label: "flakescanner.capture.session.lidar")
    private let dataQueue = DispatchQueue(label: "flakescanner.capture.data.lidar", qos: .userInitiated)
    private let session = AVCaptureSession()
    private let videoOutput = AVCaptureVideoDataOutput()
    private let depthOutput = AVCaptureDepthDataOutput()
    private var synchronizer: AVCaptureDataOutputSynchronizer?
    private var device: AVCaptureDevice?

    // Data-queue state, read under the lock once the collection is over.
    private let lock = NSLock()
    private var maps: [DepthMap] = []
    private var depthIntrinsics: PinholeIntrinsics?
    private var videoIntrinsics: PinholeIntrinsics?
    private var videoSize = (width: 0, height: 0)
    private var depthSize = (width: 0, height: 0)
    private var depthFiltered = false
    private var startTime = 0.0
    private var firstPairTime: Double?
    private var settleSamples: [ProbeMath.SettleSample] = []
    private var timestamps: [Double] = []
    private var target = 30

    private static let eightBit: Set<FourCharCode> = [kCVPixelFormatType_420YpCbCr8BiPlanarFullRange,
                                                      kCVPixelFormatType_420YpCbCr8BiPlanarVideoRange]

    private static func dims(_ format: AVCaptureDevice.Format) -> CMVideoDimensions {
        CMVideoFormatDescriptionGetDimensions(format.formatDescription)
    }

    /// Format score as in Phone LiDAR: 4:3 (the depth field of view), about 1,920 px wide, 8-bit, 30 fps.
    static func score(_ format: AVCaptureDevice.Format) -> Int {
        let d = dims(format)
        var s = 0
        if Int(d.width) * 3 == Int(d.height) * 4 { s += 1000 }
        if d.width == 1920 { s += 500 } else if d.width >= 1280 && d.width <= 2016 { s += 200 }
        if eightBit.contains(CMFormatDescriptionGetMediaSubType(format.formatDescription)) { s += 100 }
        if format.videoSupportedFrameRateRanges.contains(where: { $0.maxFrameRate >= 30 }) { s += 50 }
        if !format.isVideoBinned { s += 25 }
        return s
    }

    /// Indices of the formats with depth delivery, best score first.
    static func depthFormatIndices(of device: AVCaptureDevice) -> [Int] {
        device.formats.indices
            .filter { !device.formats[$0].supportedDepthDataFormats.isEmpty }
            .sorted { score(device.formats[$0]) > score(device.formats[$1]) }
    }

    static func depthFormat(for format: AVCaptureDevice.Format) -> AVCaptureDevice.Format? {
        let formats = format.supportedDepthDataFormats
        let width: (AVCaptureDevice.Format) -> Int32 = { dims($0).width }
        return formats.filter { CMFormatDescriptionGetMediaSubType($0.formatDescription) == kCVPixelFormatType_DepthFloat32 }
            .max { width($0) < width($1) } ?? formats.max { width($0) < width($1) }
    }

    /// Opens the LiDAR camera, collects up to `maxMaps` depth maps (or until the timeout) and closes it again.
    func collect(_ options: Options) async throws -> LidarCapture {
        guard let device = AVCaptureDevice.default(.builtInLiDARDepthCamera, for: .video, position: .back) else {
            throw CaptureError.noCamera("This iPhone has no LiDAR camera.")
        }
        self.device = device
        guard let index = options.formatIndex ?? LidarDistance.depthFormatIndices(of: device).first,
              device.formats.indices.contains(index),
              let depthFormat = LidarDistance.depthFormat(for: device.formats[index]) else {
            throw CaptureError.configuration("The LiDAR camera has no format with depth delivery.")
        }
        let format = device.formats[index]
        reset(target: options.maxMaps)

        let durationAccepted = try await onSession { [self] () -> Bool in
            var fixedDuration = false
            session.beginConfiguration()
            guard let input = try? AVCaptureDeviceInput(device: device), session.canAddInput(input) else {
                session.commitConfiguration()
                throw CaptureError.configuration("Cannot open the LiDAR camera.")
            }
            session.addInput(input)
            videoOutput.videoSettings = [kCVPixelBufferPixelFormatTypeKey as String: CaptureRig.eightBitFullRange]
            videoOutput.alwaysDiscardsLateVideoFrames = true
            guard session.canAddOutput(videoOutput), session.canAddOutput(depthOutput) else {
                session.commitConfiguration()
                throw CaptureError.configuration("Cannot read LiDAR video and depth.")
            }
            session.addOutput(videoOutput)
            session.addOutput(depthOutput)
            depthOutput.isFilteringEnabled = false
            depthOutput.alwaysDiscardsLateDepthData = true
            depthOutput.connection(with: .depthData)?.isEnabled = true
            session.commitConfiguration()

            try device.lockForConfiguration()
            device.activeFormat = format
            device.activeDepthDataFormat = depthFormat
            if let connection = videoOutput.connection(with: .video) {
                if connection.isVideoRotationAngleSupported(0) { connection.videoRotationAngle = 0 }
                if connection.isCameraIntrinsicMatrixDeliverySupported { connection.isCameraIntrinsicMatrixDeliveryEnabled = true }
            }
            let thirty = CMTime(value: 1, timescale: 30)
            if format.videoSupportedFrameRateRanges.contains(where: { $0.minFrameRate <= 30 && $0.maxFrameRate >= 30 }) {
                device.activeVideoMinFrameDuration = thirty
                device.activeVideoMaxFrameDuration = thirty
                fixedDuration = device.activeVideoMinFrameDuration == thirty && device.activeVideoMaxFrameDuration == thirty
            }
            if options.applyControls {
                if device.isFocusModeSupported(.continuousAutoFocus) { device.focusMode = .continuousAutoFocus }
            }
            device.unlockForConfiguration()

            let sync = AVCaptureDataOutputSynchronizer(dataOutputs: [videoOutput, depthOutput])
            sync.setDelegate(self, queue: dataQueue)
            synchronizer = sync
            markStart()
            session.startRunning()
            guard session.isRunning else { throw CaptureError.configuration("The LiDAR camera did not start.") }
            return fixedDuration
        }
        var exposureAccepted = false
        var focusAccepted = false

        if options.applyControls {
            // Let the camera run for a moment, then ask for the run's controls and keep collecting under them.
            try await Task.sleep(nanoseconds: 700_000_000)
            let result = await applyRunControls(device: device, format: format)
            exposureAccepted = result.exposure
            focusAccepted = result.focus
        }

        let deadline = Date().addingTimeInterval(options.timeout_s)
        while Date() < deadline {
            if isFull() { break }
            try await Task.sleep(nanoseconds: 30_000_000)
        }
        let finalState = LidarDistance.state(of: device, format: format)
        await close()

        return try assemble(format: format, depthFormat: depthFormat, state: finalState, accepts: (exposureAccepted, focusAccepted, durationAccepted))
    }

    private func reset(target newTarget: Int) {
        lock.lock(); defer { lock.unlock() }
        maps = []; depthIntrinsics = nil; videoIntrinsics = nil; firstPairTime = nil
        settleSamples = []; timestamps = []; target = max(1, newTarget)
    }

    private func markStart() {
        lock.lock(); defer { lock.unlock() }
        startTime = ProcessInfo.processInfo.systemUptime
    }

    private func isFull() -> Bool {
        lock.lock(); defer { lock.unlock() }
        return maps.count >= target
    }

    private func assemble(format: AVCaptureDevice.Format, depthFormat: AVCaptureDevice.Format, state: CameraStateRecord,
                          accepts: (exposure: Bool, focus: Bool, duration: Bool)) throws -> LidarCapture {
        lock.lock(); defer { lock.unlock() }
        guard let first = firstPairTime, !maps.isEmpty else {
            throw CaptureError.noFrames("The LiDAR camera delivered no depth maps.")
        }
        let fps = ProbeMath.rate(frames: timestamps.count, first_s: timestamps.first ?? 0, last_s: timestamps.last ?? 0)
        var capture = LidarCapture(
            maps: maps,
            depthIntrinsics: depthIntrinsics,
            videoIntrinsics: videoIntrinsics,
            videoSize_px: videoSize,
            depthSize_px: depthSize,
            formatSummary: CaptureRig.summary(format),
            depthSummary: depthSummaryText(depthFormat),
            depthIsFiltered: depthFiltered,
            timeToFirstPair_s: first - startTime,
            settleSamples: settleSamples,
            deliveredFps: fps,
            pairs: timestamps.count)
        capture.acceptsCustomExposure = accepts.exposure
        capture.acceptsLockedFocus = accepts.focus
        capture.acceptsFixedFrameDuration = accepts.duration
        capture.state = state
        return capture
    }

    private func depthSummaryText(_ format: AVCaptureDevice.Format) -> String {
        let d = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
        return "\(d.width)×\(d.height) \(CaptureRig.fourCC(CMFormatDescriptionGetMediaSubType(format.formatDescription)))"
    }

    private func close() async {
        _ = try? await onSession { [self] in
            if session.isRunning { session.stopRunning() }
            synchronizer?.setDelegate(nil, queue: nil)
            synchronizer = nil
            for input in session.inputs { session.removeInput(input) }
            for output in session.outputs { session.removeOutput(output) }
        }
    }

    private func onSession<T: Sendable>(_ work: @escaping @Sendable () throws -> T) async throws -> T {
        try await withCheckedThrowingContinuation { continuation in
            sessionQueue.async {
                do { continuation.resume(returning: try work()) } catch { continuation.resume(throwing: error) }
            }
        }
    }

    /// Applies a custom exposure at the exposure now in use and a locked lens position, as Start would.
    private func applyRunControls(device: AVCaptureDevice, format: AVCaptureDevice.Format) async -> (exposure: Bool, focus: Bool) {
        var exposureAccepted = false
        var focusAccepted = false
        let duration = device.exposureDuration
        let iso = device.iso
        let inRange = duration >= format.minExposureDuration && duration <= format.maxExposureDuration
            && iso >= format.minISO && iso <= format.maxISO
        if device.isExposureModeSupported(.custom), inRange {
            exposureAccepted = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
                sessionQueue.async {
                    do { try device.lockForConfiguration() } catch { continuation.resume(returning: false); return }
                    device.setExposureModeCustom(duration: duration, iso: iso) { _ in
                        continuation.resume(returning: device.exposureMode == .custom)
                    }
                    device.unlockForConfiguration()
                }
            }
        }
        if device.isLockingFocusWithCustomLensPositionSupported {
            focusAccepted = await withCheckedContinuation { (continuation: CheckedContinuation<Bool, Never>) in
                sessionQueue.async {
                    do { try device.lockForConfiguration() } catch { continuation.resume(returning: false); return }
                    device.setFocusModeLocked(lensPosition: device.lensPosition) { _ in
                        continuation.resume(returning: device.focusMode == .locked)
                    }
                    device.unlockForConfiguration()
                }
            }
        }
        return (exposureAccepted, focusAccepted)
    }

    private static func state(of device: AVCaptureDevice, format: AVCaptureDevice.Format) -> CameraStateRecord {
        let g = device.deviceWhiteBalanceGains
        return CameraStateRecord(
            deviceType: device.deviceType.rawValue, format: CaptureRig.summary(format), isBinned: format.isVideoBinned,
            fps: 30, distortionCorrectionSupported: device.isGeometricDistortionCorrectionSupported,
            distortionCorrectionEnabled: device.isGeometricDistortionCorrectionEnabled,
            videoHDREnabled: device.isVideoHDREnabled, stabilizationMode: "n/a", intrinsicsDeliverySupported: false,
            exposure_s: device.exposureDuration.seconds, iso: Double(device.iso), lensPosition: Double(device.lensPosition),
            whiteBalanceGains: [Double(g.redGain), Double(g.greenGain), Double(g.blueGain)],
            focusMode: device.focusMode == .locked ? "locked" : "other",
            exposureMode: device.exposureMode == .custom ? "custom" : "other", systemPressure: "n/a")
    }

    // MARK: AVCaptureDataOutputSynchronizerDelegate

    func dataOutputSynchronizer(_ synchronizer: AVCaptureDataOutputSynchronizer,
                                didOutput synchronizedDataCollection: AVCaptureSynchronizedDataCollection) {
        guard let videoSync = synchronizedDataCollection.synchronizedData(for: videoOutput) as? AVCaptureSynchronizedSampleBufferData,
              let depthSync = synchronizedDataCollection.synchronizedData(for: depthOutput) as? AVCaptureSynchronizedDepthData,
              !videoSync.sampleBufferWasDropped, !depthSync.depthDataWasDropped,
              let device else { return }
        let now = ProcessInfo.processInfo.systemUptime
        let depth = depthSync.depthData.depthDataType == kCVPixelFormatType_DepthFloat32
            ? depthSync.depthData
            : depthSync.depthData.converting(toDepthDataType: kCVPixelFormatType_DepthFloat32)
        let buffer = depth.depthDataMap
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddress(buffer) else { return }
        let w = CVPixelBufferGetWidth(buffer)
        let h = CVPixelBufferGetHeight(buffer)
        let stride = CVPixelBufferGetBytesPerRow(buffer)
        var values = [Float](repeating: .nan, count: w * h)
        for y in 0..<h {
            let row = (base + y * stride).assumingMemoryBound(to: Float.self)
            for x in 0..<w { values[y * w + x] = row[x] }
        }
        lock.lock(); defer { lock.unlock() }
        guard maps.count < target else { return }
        if firstPairTime == nil {
            firstPairTime = now
            depthFiltered = depth.isDepthDataFiltered
            depthSize = (w, h)
            if let calibration = depth.cameraCalibrationData {
                let k = calibration.intrinsicMatrix
                let ref = calibration.intrinsicMatrixReferenceDimensions
                depthIntrinsics = PinholeIntrinsics(fx_px: Double(k.columns.0.x), fy_px: Double(k.columns.1.y),
                                                    cx_px: Double(k.columns.2.x), cy_px: Double(k.columns.2.y),
                                                    referenceWidth_px: Double(ref.width), referenceHeight_px: Double(ref.height))
            }
            if let buffer = CMSampleBufferGetImageBuffer(videoSync.sampleBuffer) {
                videoSize = (CVPixelBufferGetWidth(buffer), CVPixelBufferGetHeight(buffer))
                if let k = CaptureRig.intrinsics(of: videoSync.sampleBuffer) {
                    videoIntrinsics = PinholeIntrinsics(fx_px: k[0], fy_px: k[1], cx_px: k[2], cy_px: k[3],
                                                        referenceWidth_px: Double(videoSize.width),
                                                        referenceHeight_px: Double(videoSize.height))
                }
            }
        }
        maps.append(DepthMap(width: w, height: h, values_m: values))
        timestamps.append(now)
        settleSamples.append(ProbeMath.SettleSample(time_s: now - startTime, exposure_s: device.exposureDuration.seconds,
                                                    iso: Double(device.iso)))
    }
}
