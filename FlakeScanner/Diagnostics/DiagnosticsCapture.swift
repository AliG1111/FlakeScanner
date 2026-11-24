import Foundation
import AVFoundation
import CoreMedia
import CoreMotion
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

/// How the exposure is set for a burst.
enum BurstExposure: Sendable {
    /// Automatic exposure limited to `max_s`; once settled the exposure and ISO in use are locked (as at Start).
    case autoLimited(max_s: Double)
    /// A fixed exposure and ISO (clamped to the format).
    case manual(duration_s: Double, iso: Double)
}

struct BurstRequest: Sendable {
    var deviceType: AVCaptureDevice.DeviceType = .builtInWideCamera
    var formatIndex: Int?
    var fps = 30
    var frames = 8
    var exposure: BurstExposure
    var roi: NormalizedRect
    /// Keep the ROI of every frame as an 8-bit grey picture.
    var keepImages = false
    /// Time for the automatic exposure and focus to settle before the locks, seconds.
    var settle_s = 1.2
}

/// Data of one frame (FR-APP-06 b).
struct FrameRecord: Codable, Equatable, Sendable {
    var index: Int
    var timestamp_s: Double
    /// Exposure and ISO read from the device when the frame was delivered.
    var exposure_s: Double
    var iso: Double
    var lensPosition: Double
    /// Mean brightness of the ROI (0…255).
    var roiMean: Double
    /// fx, fy, cx, cy in pixels of the frame, when the frame carried the intrinsic matrix.
    var intrinsics: [Double]?
    /// Gravity in the device frame (g), when available.
    var gravity: [Double]?
}

/// An 8-bit grey picture (the ROI of a frame).
struct GrayImage: Sendable {
    var width: Int
    var height: Int
    var pixels: [UInt8]
}

struct BurstResult: Sendable {
    var state: CameraStateRecord
    var frames: [FrameRecord]
    var series: StripSeries
    var sensorWidth_px: Int
    var sensorRows: Int
    var roiPixels: (x0: Int, y0: Int, x1: Int, y1: Int)
    var images: [GrayImage]
    /// Frames missing between delivered frames (dropped), counted from the timestamps.
    var droppedFrames: Int
    /// Exposure and ISO locked for the burst.
    var exposureUsed_s: Double
    var isoUsed: Double
    /// Frames of the burst that carried the intrinsic matrix.
    var framesWithIntrinsics: Int
}

/// Collects the frames of a burst on the data queue (the rig's frame handler).
private final class BurstCollector: @unchecked Sendable {
    private let lock = NSLock()
    private let target: Int
    private let roi: NormalizedRect
    private let keepImages: Bool
    private let rig: CaptureRig
    private let motion: CMMotionManager
    private var skip: Int
    private var active = false

    private(set) var frames: [FrameRecord] = []
    private(set) var rows: [[Double]] = []
    private(set) var images: [GrayImage] = []
    private(set) var centres: [Double] = []
    private(set) var width = 0
    private(set) var height = 0
    private(set) var bounds = (x0: 0, y0: 0, x1: 0, y1: 0)
    private var ranges: [Range<Int>] = []
    private(set) var failure: String?

    init(target: Int, roi: NormalizedRect, keepImages: Bool, skip: Int, rig: CaptureRig, motion: CMMotionManager) {
        self.target = target
        self.roi = roi
        self.keepImages = keepImages
        self.skip = skip
        self.rig = rig
        self.motion = motion
    }

    var isDone: Bool {
        lock.lock(); defer { lock.unlock() }
        return failure != nil || frames.count >= target
    }

    func start() {
        lock.lock(); active = true; lock.unlock()
    }

    func handle(_ sampleBuffer: CMSampleBuffer) {
        lock.lock(); defer { lock.unlock() }
        guard active, failure == nil, frames.count < target else { return }
        if skip > 0 { skip -= 1; return }
        guard let buffer = CMSampleBufferGetImageBuffer(sampleBuffer), CVPixelBufferGetPlaneCount(buffer) >= 1 else {
            failure = "A frame had no picture data."
            return
        }
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }
        guard let base = CVPixelBufferGetBaseAddressOfPlane(buffer, 0) else {
            failure = "A frame had no picture data."
            return
        }
        let w = CVPixelBufferGetWidthOfPlane(buffer, 0)
        let h = CVPixelBufferGetHeightOfPlane(buffer, 0)
        let stride = CVPixelBufferGetBytesPerRowOfPlane(buffer, 0)
        if frames.isEmpty {
            guard let box = roi.pixelBounds(width_px: w, height_px: h) else {
                failure = "The region is empty."
                return
            }
            width = w; height = h; bounds = box
            ranges = FlickerReadout.stripRanges(firstRow: box.y0, rows: box.y1 - box.y0)
            centres = FlickerReadout.centreRows(of: ranges)
        } else if w != width || h != height {
            failure = "The frame size changed during the burst."
            return
        }
        let luma = base.assumingMemoryBound(to: UInt8.self)
        let columns = bounds.x1 - bounds.x0
        var stripMeans: [Double] = []
        stripMeans.reserveCapacity(ranges.count)
        var total = 0.0
        var count = 0
        for range in ranges {
            var sum = 0.0
            for y in range {
                let row = luma + y * stride + bounds.x0
                var rowSum: UInt32 = 0
                for x in 0..<columns { rowSum &+= UInt32(row[x]) }
                sum += Double(rowSum)
            }
            let n = range.count * columns
            stripMeans.append(sum / Double(n))
            total += sum
            count += n
        }
        if keepImages {
            var pixels = [UInt8](repeating: 0, count: columns * (bounds.y1 - bounds.y0))
            pixels.withUnsafeMutableBufferPointer { destination in
                for y in bounds.y0..<bounds.y1 {
                    let source = luma + y * stride + bounds.x0
                    guard let start = destination.baseAddress else { return }
                    (start + (y - bounds.y0) * columns).update(from: source, count: columns)
                }
            }
            images.append(GrayImage(width: columns, height: bounds.y1 - bounds.y0, pixels: pixels))
        }
        let intrinsics = CaptureRig.intrinsics(of: sampleBuffer)
        var gravity: [Double]?
        if let g = motion.deviceMotion?.gravity { gravity = [g.x, g.y, g.z] }
        rows.append(stripMeans)
        frames.append(FrameRecord(
            index: frames.count,
            timestamp_s: CMSampleBufferGetPresentationTimeStamp(sampleBuffer).seconds,
            exposure_s: rig.device.exposureDuration.seconds,
            iso: Double(rig.device.iso),
            lensPosition: Double(rig.device.lensPosition),
            roiMean: count > 0 ? total / Double(count) : 0,
            intrinsics: intrinsics,
            gravity: gravity))
    }
}

/// Short bursts at a chosen format with locked exposure (FR-APP-06 b, design §3.8): the ROI's strip means for the
/// light check and the readout test, per-frame camera data, and optionally the ROI pictures.
enum DiagnosticsCapture {
    /// Runs one burst. Opens the camera, lets the exposure settle, locks exposure, focus and white balance, skips three
    /// frames, collects `frames` consecutive frames and closes the camera.
    static func run(_ request: BurstRequest) async throws -> BurstResult {
        guard let device = CaptureRig.backDevice(request.deviceType) else {
            throw CaptureError.noCamera("This iPhone has no such camera.")
        }
        let rig = CaptureRig(device: device)
        let motion = CMMotionManager()
        if motion.isDeviceMotionAvailable { motion.startDeviceMotionUpdates() }
        let collector = BurstCollector(target: request.frames, roi: request.roi, keepImages: request.keepImages,
                                       skip: 3, rig: rig, motion: motion)
        rig.onFrame = { [collector] buffer in collector.handle(buffer) }
        do {
            _ = try await rig.open(formatIndex: request.formatIndex, fps: request.fps)
            switch request.exposure {
            case .autoLimited(let limit):
                try await rig.setAutoExposure(maxDuration_s: limit)
                await rig.waitForExposureToSettle(minimum_s: request.settle_s, timeout_s: request.settle_s + 3)
                _ = try await rig.lockExposure(duration_s: rig.device.exposureDuration.seconds, iso: Double(rig.device.iso))
            case .manual(let duration, let iso):
                try await Task.sleep(nanoseconds: UInt64(request.settle_s * 1_000_000_000))
                _ = try await rig.lockExposure(duration_s: duration, iso: iso)
            }
            await rig.lockFocusAndWhiteBalance(lensPosition: nil, gains: nil)
            // Let the locked values reach the sensor before the frames that count.
            try await Task.sleep(nanoseconds: 300_000_000)
            let state = rig.state()
            collector.start()
            let deadline = Date().addingTimeInterval(Double(request.frames + 6) / Double(request.fps) + 4)
            while !collector.isDone && Date() < deadline {
                try await Task.sleep(nanoseconds: 20_000_000)
            }
            motion.stopDeviceMotionUpdates()
            await rig.close()
            if let failure = collector.failure { throw CaptureError.noFrames(failure) }
            guard collector.frames.count >= request.frames else {
                throw CaptureError.noFrames("Only \(collector.frames.count) of \(request.frames) frames arrived.")
            }
            var dropped = 0
            let step = 1.0 / Double(request.fps)
            for (a, b) in zip(collector.frames, collector.frames.dropFirst()) {
                dropped += max(0, Int(((b.timestamp_s - a.timestamp_s) / step).rounded()) - 1)
            }
            return BurstResult(
                state: state,
                frames: collector.frames,
                series: StripSeries(means: collector.rows, centreRows_px: collector.centres),
                sensorWidth_px: collector.width,
                sensorRows: collector.height,
                roiPixels: collector.bounds,
                images: collector.images,
                droppedFrames: dropped,
                exposureUsed_s: state.exposure_s,
                isoUsed: state.iso,
                framesWithIntrinsics: collector.frames.filter { $0.intrinsics != nil }.count)
        } catch {
            motion.stopDeviceMotionUpdates()
            await rig.close()
            throw error
        }
    }

    /// Writes a grey picture as a PNG.
    static func writePNG(_ image: GrayImage, to url: URL) throws {
        guard image.width > 0, image.height > 0, image.pixels.count == image.width * image.height else {
            throw CaptureError.configuration("A picture had no pixels.")
        }
        guard let provider = CGDataProvider(data: Data(image.pixels) as CFData),
              let cg = CGImage(width: image.width, height: image.height, bitsPerComponent: 8, bitsPerPixel: 8,
                               bytesPerRow: image.width, space: CGColorSpaceCreateDeviceGray(),
                               bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.none.rawValue),
                               provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent),
              let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
            throw CaptureError.configuration("Could not create the picture file.")
        }
        CGImageDestinationAddImage(destination, cg, nil)
        guard CGImageDestinationFinalize(destination) else {
            throw CaptureError.configuration("Could not write the picture file.")
        }
    }
}
