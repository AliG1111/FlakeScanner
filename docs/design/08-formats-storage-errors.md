# Design: on-disk formats, storage layout, error handling (§7–9)

Part of the design ([summary](../design.md)). Section numbers are stable; cite them as §N.

## 7. On-disk formats

### 7.1 General

UTF-8; CSV with a header row, units in the column names, LF line ends, "." decimals, numbers via `String(format:)`; JSON pretty-printed with ISO 8601 dates and no non-finite values. `Run.json` carries `formatVersion` (1); new fields are optional; readers ignore unknown fields. Metadata is written atomically.

### 7.2 Run folder

```
Documents/Runs/run_2026-11-23_141502/
  Run.json             settings, camera state, calibration, MD, app version; summary added at Stop
  Frames.csv           one row per analyzed frame (streamed)
  Samples.csv          one row per flake edge (Flake edges; streamed)
  FrameHistograms.csv  one row per analyzed frame, 180 × 1° bins (Edge orientation; streamed)
  Histogram.csv        run histogram, 1° bins (written at Stop)
  Summary.json         run statistics, confidence intervals, exclusions by reason (written at Stop)
  Summary.csv          the same as name,value,unit rows
  Frames/              optional: f000123_roi.png (ROI plus filter margin), f000123_full.heic, f000123_overlay.png;
                       snapshots taken during the run: s000123_*.png
  TargetReport.json    test-target runs only (§6.15), with TargetFlakes.csv
  .running             marker while the run is active

Documents/Snapshots/snapshot_2026-11-23_141502/
  Snapshot.json        settings, camera state, MD, results of the one analysis
  roi.png, overlay.png, full.heic (optional)

Documents/Diagnostics/diag_2026-11-23_141502/
  CameraReport.json (with the LiDAR report), burst_000.png …, Frames.json, Flicker.json (light check with its exposure, readout-time bursts and checks), SelfTest.json
```

### 7.3 `Run.json`

`formatVersion`, `id` (UUID), `name`, `note`, `mode` (`scan` or `target`), `startedAt`, `endedAt`, `app` {version, build}, `settingsSchema`, `device` {model, systemVersion}, `camera` {deviceType, format (width, height, fps range, binned, pixelFormat), frameDuration_s, stabilizationMode, videoHDR, lowLightBoost, distortionCorrection, exposureMode, exposureDuration_s, iso, lensPosition, whiteBalanceGains, torchLevel, intrinsics (fx, fy, cx, cy, referenceWidth, referenceHeight)?}, `roi` (normalized x, y, width, height), `roiPixels`, `roiMargin_px`, `method` {primary, both, parameters}, `flakeWidth` {px (in this run's format), source (measured / nominal / rescaled), fx_px (this run's format), measuredOn? {cameraDeviceType, formatWidth, formatHeight, fx_px, cameraDistance_mm?, measurements_px} (where the width was measured; absent for nominal)}, `rate` {requested_per_s}, `direction` {mode, angleBuffer_deg, standardError_deg, readings}, `tilt` {absolute_deg, zero_deg}, `scale` {cameraDistance_mm?, mmPerPixel?, source? (`lidar` or `manual`), spread_mm? (§6.17)}, `rollingShutter` {readout_s?, factor_s?}, `light` {flickerIndex?, flickerHz?, checkedAtStart, stripRows, brightnessReference? (per-strip means over every frame of the run's first second of moving time, §6.16)}, `conditions`? {rating, factors [{name, value, rating, remedy?}], speed_pxPerS, expectedSpeed_mmPerS?} (the forecast at Start, §6.18), `target_deg`, `limits_deg`, `quality` {thresholds}, `frameSaving` {everyN, roiPNG, fullHEIC, overlay}, `summary` (Summary.json content, at Stop), `endReason` (stop button, remote, auto-stop, low storage, interruption, MD changed, error text).

### 7.4 `Frames.csv`

`frame, method, t_s, capture_time_s, included, exclusion, n, mean_deg, mean_dev_deg, R, spread_deg, f, mad_deg, in10_pct, in20_pct, in30_pct, md_buffer_deg, speed_px_s, speed_mm_s, blur_px, exposure_s, iso, lens_position, clipped_pct, sharpness_ratio, band_common, darkest_row, psi_deg, r_rows, brightness_rel, banding_correction, tilt_abs_deg, tilt_x_deg, tilt_y_deg, analysis_ms, skipped_before, snapshot`. One row per analyzed frame and method (two rows per frame when the method is *Both*). `exclusion` = empty for an included shot, otherwise the first reason that applies, as a fixed code in this order: `clipped` (FR-QUAL-01), `blur` (FR-QUAL-03), `light_bands` (§6.2), `no_texture` (FR-QUAL-05), `md_changed` (§6.8); the screens and `Summary` name them *Clipped*, *Blur*, *Light bands*, *No texture* and *MD changed*. `mean_dev_deg` = wrap(mean − target) in (−90°, 90°]; `banding_correction` = none, rows or smoothed (§6.2); `psi_deg`, `r_rows` = ψ and R of *Edge orientation* on the row-corrected copy, on flagged shots that are not dark with a flake width of 30 px or more (empty otherwise; the first 10 decide the banding regime from ψ, §6.2); `brightness_rel` = RMS over the ROI's strips of the relative change in mean brightness from the reference (every frame of the run's first second of moving time, §6.16; empty when the exposure is not locked); `skipped_before` as §6.9. Empty cell = not available.

### 7.5 `Samples.csv`, `FrameHistograms.csv`, `Histogram.csv`

- `Samples.csv` (*Flake edges*): `frame, t_s, angle_deg, dev_deg, angle_buffer_deg, length_px, length_mm, cx, cy, contrast, pieces` (θ relative to MD, its deviation from the target; centre in normalized buffer coordinates).
- `FrameHistograms.csv` (*Edge orientation*): `frame, t_s, total_weight, b000 … b179` (weights normalized to 1 per frame; bin k = dev in (−90 + k, −89 + k]).
- `Histogram.csv`: `method, dev_start_deg, dev_end_deg, angle_start_deg, angle_end_deg, value, percent` (bins of the deviation from the target and the matching θ range; count or weight, as the run's weighting).

### 7.6 `Summary.json` / `Summary.csv`

Target, limits, duration, moving time, requested and achieved rate (shots per second of moving time, §6.9), skipped shots (due shots not taken, §6.9), mean speed, coverage and overlap, the share of moving time with the conditions forecast *Good*, *Fair* and *Poor* (§6.18), the banding regime of *Edge orientation* (`bandingRegime`: `rows`, `smoothed` or `undecided`, the frame it was decided at, the median ψ and R of the deciding shots and the number of flagged shots, §6.2; `smoothed` from the first frame below a flake width of 30 px); then one block per method (`methods`, the primary first) with weighting, frames analyzed, included and excluded by reason, samples, mean angle and mean deviation with 95 % intervals, R, spread, orientation factor, mean absolute deviation, percent within each limit (±20° with interval). `Summary.csv` prefixes each name with the method when the method is *Both*.

### 7.7 Preferences, staging, pairing

`UserDefaults`: `settings.v1` (JSON `AppSettings`), remote role and device identity (as Phone LiDAR). Remote copy staging in `Documents/RemoteStaging/` and pairing keys in the Keychain, as Phone LiDAR's design §7.20.

## 8. Storage layout

`Documents/Runs/` (one folder per run, Files-app visible via `UIFileSharingEnabled` and `LSSupportsOpeningDocumentsInPlace`), `Documents/Snapshots/` (snapshots taken outside a run), `Documents/Diagnostics/` (probe results until shared and deleted), `Documents/RemoteStaging/` (partial copies on the remote). Start is refused below 1 GB free; a run stops and saves below 300 MB (checked every 10 s).

## 9. Error handling

User-facing `LocalizedError` types (`CaptureError`, `RunError`, remote errors as Phone LiDAR). Captured data is never deleted on failure; the first failed write stops the run and saves what it has; camera interruptions stop and save a run and restart the camera when possible; an analysis input that does not fit (size change, missing plane) skips the shot with a counted reason instead of trapping; no `try?` on paths that read or write measurement data.

