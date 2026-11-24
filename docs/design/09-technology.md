# Design: technology recommendations (§10)

Part of the design ([summary](../design.md)). Section numbers are stable; cite them as §N.

## 10. Technology recommendations

### 10.1 Summary

| Area | Decision | Main reason |
|---|---|---|
| Language / UI | Native Swift + SwiftUI + Observation (UIKit bridges) | Full camera control, Accelerate, Network framework, and Phone LiDAR's code. |
| Capture | AVFoundation video data output, one physical camera | Manual exposure, focus and format control at 30–60 fps; no lens switching. |
| Image processing | Accelerate (vImage, vDSP, vForce) + plain Swift for region growing | Fast, deterministic, on every iPhone and in the simulator; no dependency. |
| Measurement methods | Own LSD-style edge detector with collinear merging (default) + structure tensor | Most accurate in the lab (§6.13); sub-pixel; no license issue. |
| Machine direction | Phase correlation + ZNCC refinement | Any direction, sub-pixel, rigid-motion model. |
| Remote link | Phone LiDAR's Network framework + CryptoKit link, ported | Owner-approved, reviewed and tested design. |
| Project / CI / install | XcodeGen, GitHub Actions `macos-26`, Sideloadly or TestFlight | The owner's working setup without a Mac. |
| Tests | XCTest host-less bundle on the simulator; Python lab for research | Pure logic tested in CI; algorithms prototyped where Python runs. |
| Persistence | Plain files (JSON, CSV, PNG/HEIC) | Excel and scripts on Windows, Files app. |

### 10.2 Native Swift vs Flutter, React Native, Unity
The app needs low-level AVFoundation control (custom exposure, focus lock, format selection, intrinsics), Accelerate for per-frame maths and the Network framework for the peer-to-peer link. Cross-platform frameworks would need native plugins for all of it, copy large frames across a bridge and still need Xcode. Native Swift also lets the app reuse Phone LiDAR's code. Chosen: native.

### 10.3 Capture API
- AVFoundation video data output: full manual control, high frame rates, intrinsics per frame. Chosen.
- ARKit: gives LiDAR depth and device pose, but takes over the camera with fixed formats and limited exposure control; not used. LiDAR depth comes from AVFoundation's LiDAR depth camera (`builtInLiDARDepthCamera`), as in Phone LiDAR's Line scan (§6.17).
- Still photos (`AVCapturePhotoOutput`, 24/48 MP): higher resolution per shot but lower rates, and the photo pipeline's multi-frame fusion must be avoided with moving material (quality prioritization *speed*, no fusion, or Bayer RAW). Kept as an option to evaluate in P8 if the video image processing (denoise, sharpening, tone mapping) turns out to limit accuracy (R-14).

### 10.4 Image processing library
- Accelerate + Swift: chosen. Enough for a few shots per second at full resolution; Metal compute only if profiling (P8) shows a need.
- OpenCV: complete toolbox (it is what the lab uses), but a large C++ binary, C++ interop that cannot be debugged without a local compiler, and its LSD's licensing history. Not used in the app.
- Vision framework (`VNDetectContoursRequest`, `VNTranslationalImageRegistrationRequest`): less control over sub-pixel accuracy, thresholds and determinism. Not used for measurements. Core ML is the route for the later ML method (P10).

### 10.5 Edge detection
Hough transform (angle quantization, poor with many short overlapping edges), Canny + contour fitting (threshold-sensitive, edges broken at junctions), LSD-style line-support regions (sub-pixel orientation, almost parameter-free, false-detection control). Chosen: LSD-style, own implementation, plus collinear merging for occlusion.

### 10.6 Orientation field
Structure tensor (local, gives coherence for quality weighting), 2-D FFT power spectrum (global, window artefacts, no local quality), Gabor filter bank (angle quantization, more computation). Chosen: structure tensor.

### 10.7 Machine-direction estimation
Phone LiDAR's SAD pyramid tracker measures movement along the buffer rows with a small across range, which suits speed but not a precise direction at any phone rotation. Phase correlation handles any direction with sub-pixel accuracy and is cheap with vDSP. Chosen: phase correlation with ZNCC refinement.

### 10.8 Build, CI and distribution
Identical to Phone LiDAR (its design §10.3–10.5): XcodeGen because there is no Mac to edit `.pbxproj`; GitHub Actions `macos-26` (unlimited standard-runner minutes for public repositories; a private repository consumes the account's macOS minutes); unsigned `.ipa` for Sideloadly with a free Apple ID (7-day signing; the free ID allows 3 apps, so Phone LiDAR and Flake Scanner fit), optional TestFlight job with `codemagic-cli-tools`.

### 10.9 Swift language mode
Swift 5 mode, as Phone LiDAR, so the ported remote link compiles as reviewed, with the concurrency rules of §5. Swift 6 from day one would add compile-time race checking, but every compile costs a CI round trip here and the port would need rework first; the Swift 6 migration is a backlog item for both apps.

### 10.10 Remote link transport and security
Phone LiDAR's decisions carry over (its design §10.10): direct peer-to-peer Wi-Fi with the Network framework, CryptoKit handshake with a 6-digit pairing code, ChaChaPoly channel. The same limitation applies: a 6-digit code cannot stop an attacker who is active at the pairing moment (no PAKE in CryptoKit); later sessions use a 256-bit key.

### 10.11 Reuse of Phone LiDAR code
Port (copy with renames and small adapters) the files listed in §3.7, the parts of `Storage/Formatting.swift` listed in §3.6, `App/KeepScreenOn.swift`, `App/CameraAccess.swift`, the CI workflow and the XcodeGen spec from Phone LiDAR at `1ac68a7`, keeping their unit tests. A shared Swift package used by both apps would avoid duplication but needs a third repository and changes to Phone LiDAR; it is in the backlog (R-12).

### 10.12 Separate app vs a mode in Phone LiDAR
The owner asked for an app. A separate app keeps Phone LiDAR's validated code untouched, gives operators a focused screen, and releases independently; the cost is the duplicated remote code and a second app to install. Chosen: separate app.

### 10.13 Python lab
`tools/lab` (numpy + OpenCV) runs in the cloud workspace: synthetic mats with known angles, estimator comparisons, fixture images and reference results for the Swift parity tests (NFR-TST-02), the test-target generator, and later offline checks of saved frames. Development only; never shipped; not needed to build the app.

