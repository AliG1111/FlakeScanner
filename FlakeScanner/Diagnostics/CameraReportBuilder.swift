import Foundation
import AVFoundation
import UIKit

/// Builds the camera report (FR-APP-06 a) from the phone's back cameras. Device only.
enum CameraReportBuilder {
    static let deviceTypes: [AVCaptureDevice.DeviceType] = [
        .builtInWideCamera, .builtInUltraWideCamera, .builtInTelephotoCamera, .builtInLiDARDepthCamera,
    ]

    @MainActor
    static func build() -> CameraReport {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd HH:mm:ss Z"
        let device = DeviceInfo(model: modelIdentifier(), systemVersion: UIDevice.current.systemName + " " + UIDevice.current.systemVersion,
                                appVersion: AppInfo.versionText(Bundle.main.infoDictionary ?? [:]),
                                date: formatter.string(from: Date()))
        var cameras: [CameraInfo] = []
        for type in deviceTypes {
            guard let camera = AVCaptureDevice.default(type, for: .video, position: .back) else { continue }
            cameras.append(info(camera))
        }
        return CameraReport(device: device, cameras: cameras)
    }

    private static func info(_ camera: AVCaptureDevice) -> CameraInfo {
        let formats = camera.formats.map { format -> FormatInfo in
            let size = CaptureRig.dimensions(format)
            let rates = format.videoSupportedFrameRateRanges
            let depth = format.supportedDepthDataFormats.map { d -> DepthFormatInfo in
                let dims = CMVideoFormatDescriptionGetDimensions(d.formatDescription)
                let depthRates = d.videoSupportedFrameRateRanges
                return DepthFormatInfo(width_px: Int(dims.width), height_px: Int(dims.height),
                                       pixelFormat: CaptureRig.fourCC(CMFormatDescriptionGetMediaSubType(d.formatDescription)),
                                       minFps: depthRates.map(\.minFrameRate).min(), maxFps: depthRates.map(\.maxFrameRate).max(),
                                       isFiltered: nil)
            }
            return FormatInfo(width_px: size.width, height_px: size.height,
                              pixelFormat: CaptureRig.fourCC(CMFormatDescriptionGetMediaSubType(format.formatDescription)),
                              minFps: rates.map(\.minFrameRate).min() ?? 0, maxFps: rates.map(\.maxFrameRate).max() ?? 0,
                              isBinned: format.isVideoBinned, supportsVideoHDR: format.isVideoHDRSupported,
                              fieldOfView_deg: Double(format.videoFieldOfView),
                              minISO: Double(format.minISO), maxISO: Double(format.maxISO),
                              minExposure_s: format.minExposureDuration.seconds, maxExposure_s: format.maxExposureDuration.seconds,
                              maxZoomFactor: Double(format.videoMaxZoomFactor), depthFormats: depth)
        }
        let focus = camera.minimumFocusDistance
        return CameraInfo(name: camera.localizedName, deviceType: camera.deviceType.rawValue, position: "back",
                          supportsDistortionCorrection: camera.isGeometricDistortionCorrectionSupported,
                          distortionCorrectionEnabled: camera.isGeometricDistortionCorrectionEnabled,
                          supportsLowLightBoost: camera.isLowLightBoostSupported,
                          minFocusDistance_mm: focus > 0 ? focus : nil,
                          supportsLockedLensPosition: camera.isLockingFocusWithCustomLensPositionSupported,
                          supportsCustomExposure: camera.isExposureModeSupported(.custom),
                          formats: formats, intrinsicsDeliverySupported: nil, activeFormatSummary: nil)
    }

    private static func modelIdentifier() -> String {
        var system = utsname()
        uname(&system)
        let mirror = Mirror(reflecting: system.machine)
        let identifier = mirror.children.reduce("") { text, element in
            guard let value = element.value as? Int8, value > 0 else { return text }
            return text + String(UnicodeScalar(UInt8(bitPattern: value)))
        }
        return identifier.isEmpty ? UIDevice.current.model : identifier
    }
}
