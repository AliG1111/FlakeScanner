# Design: modules (§3)

Part of the design ([summary](../design.md)). Section numbers are stable; cite them as §N.

## 3. Modules

Pure files (marked **pure**) use Foundation and Accelerate only, have no device dependencies and are compiled into the host-less test bundle.

### 3.1 App (`App/`)

| File | Responsibility |
|---|---|
| `FlakeScannerApp.swift` | App entry; creates `RunStore`, `RemoteLink`, `AppSettings`; scene-phase handling. |
| `HomeView.swift` | Scan, Connect to the other phone, Runs, Settings / About (version, build and a link to the user guide). |
| `AppInfo.swift` | **pure** version and build text for About from the bundle's info dictionary (P0.3). |
| `AppSettings.swift` | **pure** `Codable` settings (`ScanSettings`: ROI, rate, method and parameters, exposure, focus, torch, MD mode, target, limits, frame saving, the highest expected speed for the conditions forecast) with defaults, validation (`clamped()`), persistence as JSON in `UserDefaults` (`settings.v1`). The same type is the remote's settings payload. |
| `KeepScreenOn.swift`, `CameraAccess.swift` | Ported from Phone LiDAR (`ScreenAwake` holders, permission flow). |

### 3.2 Capture (`Capture/`)

| File | Responsibility |
|---|---|
| `CapturePipeline.swift` | `AVCaptureSession` with one physical back camera; format choice (§6.10); stabilization off, distortion correction on, intrinsic matrix delivery on; exposure / focus / white balance / torch control and locks; `AVCaptureVideoDataOutput` (`420f`, `alwaysDiscardsLateVideoFrames`) on the data queue; per-frame motion estimation, shot selection, ROI copy into pooled buffers, hand-off to the analysis queue; preview frames for the remote; interruption, runtime-error and system-pressure observers. Device code, not in the test target. |
| `CameraFormats.swift` | **pure** ranking of candidate formats (resolution, maximum frame rate, binning) described by plain values, so the choice is unit-tested. |
| `ExposurePlanner.swift` | **pure** blur budget → longest shutter; ISO needed for a target brightness; blur estimate per frame (§6.10). |
| `ShotScheduler.swift` | **pure** shot selection by timestamp, skip accounting, achieved rate, pause rules (§6.9). |
| `LevelMonitor.swift` | CoreMotion gravity → tilt (Phone LiDAR's convention), read on the data queue. |
| `ConditionsForecast.swift` | **pure** expected result quality from speed and light: light for the speed (ISO needed and the image noise it brings against the mat's contrast), blur, movement per frame, flicker and light bands; worst-factor rating with remedies and a 3 s hold (§6.18). |
| `LidarDistance.swift` | LiDAR depth camera session for the distance reading at Start and on demand (§6.17): a format with depth delivery, unfiltered `DepthFloat32` maps paired with video by `AVCaptureDataOutputSynchronizer` (Phone LiDAR's Line scan setup); session changes on the session queue, maps on the data queue; device only. |
| `CameraScale.swift` | **pure** ROI footprint in the depth map, median distance and spread, validity checks, mm per px from the distance and fₓ (§6.17). |

### 3.3 Motion (`Motion/`)

| File | Responsibility |
|---|---|
| `PhaseCorrelator.swift` | **pure** windowed phase correlation with vDSP 2-D FFT, sub-pixel peak. |
| `MotionEstimator.swift` | **pure** coarse shift (phase correlation at ¼ scale) and fine shift (ZNCC at full scale, sub-pixel), quality (§6.8). |
| `DirectionTracker.swift` | **pure** MD estimate from accepted shifts: robust vector mean, standard error, *Detected* state, drift during a run, line-stopped state, smoothed speed. |

### 3.4 Analysis (`Analysis/`)

| File | Responsibility |
|---|---|
| `LumaImage.swift` | **pure** Float32 planar image (row-major, explicit stride), crop, 8-bit conversion; `NormalizedRect` ↔ pixel rectangles with filter margins. |
| `Kernels.swift` | **pure** Gaussian and derivative-of-Gaussian kernels; separable convolution (vImage) with reflected borders. |
| `RowNormalizer.swift` | **pure** banding correction for *Edge orientation*: each sensor row divided by its mean (*Rows* regime) or by the moving average of the row means over 0.7 flake widths, at most 25 rows (*Smoothed* regime) (§6.2). |
| `TensorOrientation.swift` | **pure** structure tensor and the *Edge orientation* estimator (§6.4). |
| `EdgeSegmentDetector.swift` | **pure** line-support-region detector for straight flake edges (§6.5). |
| `CollinearMerger.swift` | **pure** joins pieces of one edge split by crossing flakes (§6.5 step 8). |
| `FlakeWidth.swift` | **pure** coarse flake-width estimate from paired long edges, the cross-check of the set width (§6.5, FR-CAL-07). |
| `AngleFrame.swift` | **pure** buffer angles → angles relative to MD with the app's sign convention (§6.1). |
| `QualityMetrics.swift` | **pure** clipping, sharpness, common band gradient and darkest row, strip brightness, texture checks (§6.10); the ROI's contrast s for the conditions forecast (§6.18). |
| `FrameAnalyzer.swift` | **pure** one shot: quality metrics on the raw ROI → *Flake edges* on the raw ROI and *Edge orientation* on the raw ROI or, on a flagged shot, on the copy corrected in the run's banding regime (an input from `RunAggregator`); the banding rules may exclude the shot for one or both methods, and with a flake width of 30 px or more a flagged shot also returns the strands' direction to the rows (ψ, R) for the regime (§6.2) → `FrameResult` (accumulator, samples, quality, overlay primitives, timing). |
| `SyntheticMat.swift` | **pure** deterministic Swift renderer of strand mats with known angles (seeded PCG generator) for the accuracy tests (NFR-ACC-02 conditions over many seeds, rotation, determinism), checked against its own truth; optional PWM bands as the lab's (duty, period, exposure in rows, off level, along either sensor axis) for the banding tests (§6.2). It follows the lab's model but is not bit-identical to it, so parity with the lab uses the lab's fixture images instead (§6.13, NFR-TST-02). |

### 3.5 Statistics (`Statistics/`)

| File | Responsibility |
|---|---|
| `AxialAccumulator.swift` | **pure** weighted doubled-angle sums, within-limit sums, absolute deviation, 1° histogram; `merge`; derived `AxialSummary` (§6.6). |
| `RunAggregator.swift` | **pure** frame inclusion and exclusion counts, run accumulator, per-frame sums for confidence intervals, rolling windows, time series (§6.6); holds each shot through the MD-change confirmation before adding it (§6.8 step 7); decides and keeps the banding regime of *Edge orientation* for flake widths of 30 px or more (from the median ψ of the run's first 10 flagged shots that are not dark, undecided until then, §6.2) and the share of recent shots with bands for the forecast (§6.18). |
| `Coverage.swift` | **pure** ROI length along MD, overlap, coverage, rate without overlap (§6.11). |

### 3.6 Scan (`Scan/`), Runs (`Runs/`), Library (`Library/`), Storage (`Storage/`)

| File | Responsibility |
|---|---|
| `Scan/ScanView.swift`, `ScanModel.swift` | Scan screen (portrait, Phone LiDAR layout pattern), run states, start/stop rules, settings sheet, conformance to `RemoteScannerTarget`. |
| `Scan/ROIEditor.swift` | ROI drawing view shared by the scanner and the remote (draw, move, resize; normalized output; minimum size). |
| `Scan/CameraPreview.swift`, `OverlayView.swift` | Preview layer and overlays (ROI, MD arrow and "+" arc, edges coloured by angle). |
| `Scan/LiveStatsPanel.swift`, `QualityPanel.swift` | Fixed-cell readouts, mini histogram, quality light and reasons. |
| `Runs/RunStore.swift` | **pure core** run folders, list, load, rename, notes, delete, sizes. It tracks the active run, which stays read-only (no rename, note, delete, share or copy to the other phone) and is skipped by the recovery scan while it is active (NFR-REL-02). It clears the active run only after the recorder has closed the run's files, at the end of Stop or after the run stopped with an error; after an error it starts a recovery scan, so that run is repaired and listed in the same launch. |
| `Runs/RunFormats.swift` | **pure** `Run.json` model, CSV headers and row encoders (§7). |
| `Runs/RunRecorder.swift` | Streams `Frames.csv`, `Samples.csv` / `FrameHistograms.csv`, frame images; writes summaries at Stop; marker file (holding this app launch's ID); queue-confined to the run I/O queue. At every flush (at least once a second) it checks that the run folder still exists: if it was moved or deleted (for example in the Files app, where writes to removed files would fail silently), the run stops with a `LocalizedError` and nothing is deleted. On any error stop it writes the error text as `endReason` in `Run.json` when it still can, closes its files and leaves the marker for the recovery scan. |
| `Runs/RunRecovery.swift` | **pure core** repair of cut-off CSV/JSON and recovery of interrupted runs. It recovers folders whose `.running` marker holds another app launch's ID, and folders whose marker holds this launch's ID once `RunStore` no longer reports their run as active (a run that stopped with an error), so the run being recorded is never touched and an error-stopped run does not wait for the next launch. The scan takes the active run from `RunStore` when it starts; Start waits for a running scan to finish, so no run begins during a scan. The scan runs at launch, when the library opens and after a run stops with an error. A recovered run is listed as incomplete with its `endReason`: the error text the recorder wrote, or `interruption` when there is none. |
| `Library/*` | Runs list, run screen, `HistogramChart`, `RoseChart` (Swift Charts / `Canvas`), `TimeSeriesChart`, frame browser, share. |
| `Storage/Formatting.swift` | `Units.bytes` and `CSV.escape` / `CSV.make` from Phone LiDAR's `Storage/Formatting.swift`, plus `Num.fixed` (locale-independent fixed decimals) (P0.3). Copied when first needed: `TextFileWriter` and `SpeedText` from Phone LiDAR's `Line/LineRecording.swift`, `JSONEncoder.pretty` and `JSONDecoder.iso` from its `Storage/ScanStore.swift` (P5, P6). |

### 3.7 Remote (`Remote/`)

Ported from Phone LiDAR `Remote/` (design §3.9 and §6.15 there) with renames (`_flakescan._tcp`, transcript label `FlakeScanner remote link v1`, queue `flakescanner.remote.link`) and these changes:

| File | Change |
|---|---|
| `RemoteProtocol.swift` | **pure** `RemoteStatus` replaced by the scanner status of FR-RMT-06; new messages and the preview record (§6.14); commands for settings patches, ROI, snapshot, MD detection, refocus; settings schema version in the hello and the status. |
| `RemoteCrypto.swift`, `RemoteKeychain.swift`, `RemoteConnection.swift`, `RemoteDiscovery.swift` | Unchanged apart from names. |
| `RemoteTransfer.swift` | Adapted: Phone LiDAR's `RemoteImport.record` returns its `ScanRecord` and `RemoteFiles` withholds `scan.json` because the remote writes its own. Here a run folder is copied whole: `Run.json` is measurement data, so it is copied byte for byte, never regenerated; the import decodes it to validate it and registers the run with `RunStore`. |
| `RemotePreview.swift` | **pure** preview header, overlay encoding (quantized segments), size limits; JPEG encode/decode helpers (ImageIO) kept in a device file. |
| `RemoteLink.swift` | Scanner side gains preview subscription and settings/ROI commands through `RemoteScannerTarget`; remote side gains preview display and settings editing. |
| `RemoteControlView.swift`, `RemoteLinkViews.swift` | Remote screen with the live preview, `ROIEditor`, controls, statistics and the runs list with copy (uses `SpeedText`, copied with it). |

Exact port sources at `1ac68a7`: `PhoneLidar/Remote/` (`RemoteConnection`, `RemoteControlView`, `RemoteCrypto`, `RemoteDiscovery`, `RemoteKeychain`, `RemoteLink`, `RemoteLinkViews`, `RemoteProtocol`, `RemoteTransfer`), `Line/LineRecording.swift` (`SpeedText`, `TextFileWriter` only), `Storage/ScanStore.swift` (JSON coder extensions only), `App/KeepScreenOn.swift`, `App/CameraAccess.swift`, `Line/LineCapturePipeline.swift` (the LiDAR depth session setup only, for `LidarDistance`; ported in P0.7, ahead of the rest, because the probe build needs it), and the tests `RemoteConnectionLoopbackTests`, `RemoteCryptoTests`, `RemoteProtocolTests`, `RemoteRulesTests`, `RemoteTransferTests`. The port (P6.1) first adds the small adapters these files need to compile here (`SpeedText`, a run record in place of `ScanRecord`, the store calls), then changes behaviour in later tasks.

### 3.8 Diagnostics (`Diagnostics/`) and test target (`Target/`)

| File | Responsibility |
|---|---|
| `Diagnostics/CameraReport.swift` | **pure** camera capability report from plain format values (size, frame-rate range, binning, HDR, distortion correction, intrinsics delivery, exposure and ISO ranges) and the LiDAR report (the depth camera's formats with depth delivery, depth map size, which of custom exposure, locked focus and fixed frame durations it accepts, the measured time to switch cameras and back and to settle, the distance reading) as text and JSON (FR-APP-06, §6.17). |
| `Diagnostics/DiagnosticsCapture.swift` | Device: short bursts at a chosen format with locked exposure; ROI PNGs and per-frame camera data. |
| `Diagnostics/FlickerReadout.swift` | **pure** light check (flicker index, flicker frequency and mains frequency from a burst at 1/27 s, DFT bins 4, 6, 8 and 12 of each strip) and readout time (phase slope of the flicker bin across the strips of a burst at an exposure of 1/(2F), with its plausibility checks) (§6.16); used by Diagnostics (P0.7) and by the light check at Start (P3.1). |
| `Diagnostics/SelfTest.swift` | **pure** runs the bundled fixture images (`FlakeScanner/Diagnostics/Fixtures/`, copied from `tools/lab/fixtures/`) through `FrameAnalyzer` and compares with their stored results. |
| `Diagnostics/DiagnosticsView.swift`, `DiagnosticsExport.swift` | Screen and the zip export (directory zipped by `NSFileCoordinator` for upload). |
| `Target/TargetLayout.swift` | **pure** `Codable` layout of a printed target: markers, reference bar, flakes with their angles and positions (version 1 bundled; generated with the PDF by `tools/lab`). |
| `Target/TargetDetector.swift` | **pure** marker detection, homography from the four markers, reference-bar angle (§6.15). |
| `Target/TargetTracker.swift` | **pure** follows the four markers of a moving sheet in every camera frame on the data queue, with small local templates; travel direction and taping angle from the track (§6.15 step 5). |
| `Target/TargetMatcher.swift` | **pure** matches detected edges to printed flakes, per-flake errors, the target report. |
| `Target/TargetReportView.swift` | Report screen (measured against printed, per-angle bias). |

