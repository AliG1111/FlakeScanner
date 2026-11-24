@preconcurrency import AVFoundation
import UIKit

/// Camera permission helper (ported from Phone LiDAR). Without it a denied camera only shows nothing.
enum CameraAccess {
    /// True when the camera may be used. Asks the first time.
    static func request() async -> Bool {
        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            return true
        case .notDetermined:
            return await AVCaptureDevice.requestAccess(for: .video)
        default:
            return false
        }
    }

    @MainActor
    static func openSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
}
