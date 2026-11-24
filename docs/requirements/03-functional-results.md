# Requirements: functional, statistics, quality, calibration, runs, library, remote (§5.7–5.12)

Part of the requirements ([summary](../requirements.md)). Section numbers are stable; cite them as §N.

### 5.7 Statistics (FR-STAT)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-STAT-01 | Per analyzed frame: n, mean angle, alignment R, spread, orientation factor, mean absolute deviation, percent within ±10/20/30° (limits configurable), quality flags. | P1, P2, P3 | Planned |
| FR-STAT-02 | Per run, over the included frames: the same values plus the histogram (5° bins, 1/2/10° selectable), a rose plot, the 95 % confidence interval of the mean angle and of the percent within ±20° (computed from the variation between frames, design §6.6), and frames included and excluded with reasons. | P1, P2, P4, P5 | Planned |
| FR-STAT-03 | Rolling statistics over the last 10 s or 60 s (selectable) and time-series charts of mean angle, spread and percent within ±20° during and after a run. | P4, P5 | Planned |
| FR-STAT-04 | Target direction (0°, 90° or custom): deviation, orientation factor and percent-within values are relative to it; angles are displayed in (target − 90°, target + 90°] and files add the signed deviation (§4.1). | P1, P4 | Planned |
| FR-STAT-05 | All statistics use the axial formulas of §4.2; histograms are over the deviation from the target, (−90°, 90°]. | P1 | Planned |
| FR-STAT-06 | Live values update at ≤ 4 Hz in fixed-width cells with fixed decimals (angles 0.1°, percentages 0.1 %). | P4 | Planned |
| FR-STAT-07 | Minimum sample count before statistics are shown: default 30 samples per frame for frame values and 200 per run for run values. | P1, P4 | Planned |
| FR-STAT-08 | Flake size statistics (later): distributions of the visible edge length and the paired-edge width of *Flake edges*, in mm with the scale (FR-CAL-02, FR-CAL-03); overlapped flakes read short, so lengths are visible lengths. | P9 | Planned (later) |

### 5.8 Measurement quality (FR-QUAL)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-QUAL-01 | Exposure: share of ROI pixels clipped dark or bright; warning above 1 %, frame excluded above 5 % (configurable). | P1, P3 | Planned |
| FR-QUAL-02 | Focus: sharpness of the ROI compared with the value at focus lock; warning when it drops by more than 30 %. | P1, P3 | Planned |
| FR-QUAL-03 | Motion blur budget: blur (px) = speed (px/s) × exposure time (s). Warning above 1.0 px, frame excluded above 2.0 px (configurable). In Auto exposure the longest shutter = budget / speed. Setup shows the shutter the budget needs (budget × mm/px ÷ speed, for example 1/2,800 s at 1,000 mm/s and 0.36 mm/px) and whether the light allows it at the primary method's ISO limit (design §6.18: provisionally 1,600 for *Flake edges*, 6,400 for *Edge orientation*). | P1, P2, P3 | Planned |
| FR-QUAL-04 | Lighting flicker: (a) banding (PWM-dimmed lights and other flicker with dark phases, seen through the rolling shutter as bands along the sensor rows) is measured in every shot from the row profiles of the raw ROI (common band gradient and darkest row, design §6.2, §6.10); (b) mains flicker by a light check at Start, right after the exposure lock (on demand also in Setup): a 1 s burst at a frame duration of 1/27 s, which is a whole number of flicker periods at neither 50 nor 60 Hz (flicker index and flicker frequency, design §6.16); (c) during a run with the exposure locked, the brightness of each strip of the ROI is compared with its mean over every frame of the run's first second of moving time (brightness drift; it shows lamps that change and the slow beat of 60 Hz flicker against the camera clock, which the run's fixed 1/30 s frames hide). (b) and (c) give a warning (*Light flickers*, *Light changed*). Under (a), a shot with near-dark rows is excluded for both methods (*Light bands*), because no correction recovers its angles; *Flake edges*, which cannot be corrected, is excluded from weak bands on (*Light bands*), and when the bands are strong enough to matter *Edge orientation* is corrected in *Auto* (FR-MEAS-04) in the run's regime, chosen from the strands' direction to the sensor rows and the flake width, or excluded where the correction cannot follow the bands (lab E4, design §6.2). So banding mostly costs shots rather than accuracy; bands below the flags can still move angles a little (design §6.2). | P1, P2, P3 | Planned |
| FR-QUAL-05 | Texture: too few samples or too little edge strength excludes the frame ("no texture"). | P1 | Planned |
| FR-QUAL-06 | Level: the absolute tilt of the camera axis from vertical (gravity, FR-CAL-01): amber above 1°, red above 3°. Zeroing the level never moves these limits. The absolute tilt is recorded per frame and in `Run.json`. | P3 | Planned |
| FR-QUAL-07 | A quality light (green / amber / red) with the reasons on the scanner and the remote; each frame's quality values and flags are saved, and exclusions are counted by reason in the run summary. | P4, P5 | Planned |
| FR-QUAL-08 | **Conditions forecast** (owner, 2026-11-23): before and during a run the app tells the user whether the results will be good, fair or poor for the line speed and the light available (design §6.18). It rates the light against the shutter the speed needs (the ISO it takes, so image noise), the motion blur at the shutter in use, the movement per frame against the motion estimator's range, flicker once the light check has run, and the share of shots with light bands; the worst gives *Good*, *Fair* or *Poor*. Each factor names its remedy (for example "about 3 × more light", a slower line, a higher mount). While the line is stopped the forecast uses the highest expected speed (Setup, default 1,000 mm/s), and Setup also shows the forecast at that speed. *Fair* and *Poor* factors join the quality light's reasons and *Poor* shows a banner on the scan screen and the remote; Start stays allowed. The forecast at Start and the share of moving time under each rating are recorded. | P0, P1, P2, P3, P4, P5 | Planned |

### 5.9 Calibration and setup (FR-CAL)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-CAL-01 | Bubble level from gravity showing the absolute tilt; an optional zero (and reset), as Phone LiDAR, only sets the reference used to detect bumps during a run. | P3 | Planned |
| FR-CAL-02 | Scale: the camera's distance to the mat is measured with the iPhone's LiDAR at Start and on demand in Setup (the camera height varies from mount to mount, Q-02; design §6.17) and combined with the camera intrinsics to give mm per px. Without a valid LiDAR reading the distance can be entered (mm); without either, sizes and speeds stay in px. The run records the distance, its source and its spread. | P0, P3, P8 | Planned |
| FR-CAL-03 | LiDAR surface tilt: a perspective correction of the analysis from the depth map (the distance itself is FR-CAL-02). | P9 | Planned (later) |
| FR-CAL-04 | Rolling-shutter readout calibration and correction. | P9 | Planned (later) |
| FR-CAL-05 | Lens-distortion correction from the camera's calibration data. | P9 | Planned (later) |
| FR-CAL-06 | **Test-target mode** (design §6.15): a printable target (PDF and layout file generated by `tools/lab`) with four corner markers, a printed reference bar with an arrow (the reference direction and sign) and flakes at known angles. The app finds the markers and the bar, uses the bar as MD when the sheet lies still (no movement needed, no stopped-line pause), analyses the frames, and reports measured against printed statistics (mean, spread, percent within ±20°) and the per-angle bias of flakes matched through the markers. Taped to the moving belt, the travel direction comes from the markers' track: the report checks the automatic MD against it and corrects the printed angles by the measured taping angle (between the bar and the travel). Results are saved as a run with a target report. | P2, P5, P8 | Planned |
| FR-CAL-07 | **Flake width** (required setup, design §6.5): the typical flake width in px is set before the first run on a mount, by dragging across three to five typical flakes on a frozen frame (the app uses the second-widest, because a width set too narrow lets flake ends pass as edges and inflates the spread, while one set up to twice too wide costs little, lab E10) or from the nominal width in mm with the scale. Start is refused until it is set; it is recorded in every run. It is stored with the camera and format it was measured on, together with that format's focal length in px (fx, from the intrinsics or the field of view) and the camera distance (FR-CAL-02; a LiDAR reading taken when the width is set, never an earlier one, which may come from another mount): a format change on the same camera rescales it by the ratio of fx, a new camera distance by the inverse ratio of the distances, and a camera change asks for a new measurement; when either distance is missing, Start asks to confirm the width or measure it again. An automatic estimate from paired flake edges warns when the setting is below 0.75 × or above 2 × the estimate (lab E10, E11; P2.1 improves the estimate and tunes the limits). Below 12 px per flake width the screen warns (move closer or use the telephoto). | P2, P4 | Planned |

### 5.10 Runs and recording (FR-RUN)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-RUN-01 | Start and Stop on the scanner and from the remote; states: *not ready* (with the reason), *ready*, *running*, *saving*, *failed*. | P4 | Planned |
| FR-RUN-02 | Each run is a folder `run_<yyyy-MM-dd_HHmmss>` with `Run.json` (settings, camera state, calibration, MD, flake width, app version; written at Start, when the run appears in the library marked *Recording*, and completed at Stop), `Frames.csv` (one row per analyzed frame and method), `Samples.csv` (one row per sample, Flake edges) and/or `FrameHistograms.csv` (Edge orientation), `Histogram.csv` and `Summary.json` / `Summary.csv`. Formats in design §7. | P5 | Planned |
| FR-RUN-03 | Optional frame saving: every Nth analyzed frame's ROI with its filter margin (the margin is recorded in `Run.json`, so a re-analysis reproduces the results) as a lossless 8-bit PNG, optionally the full frame (HEIC) and the overlay picture; the screen shows the expected storage per minute. | P5 | Planned |
| FR-RUN-04 | Free space: Start is refused below 1 GB; a run stops and saves below 300 MB. | P5 | Planned |
| FR-RUN-05 | Crash safety: results are streamed to disk during the run (rows held for the MD-change check, a few seconds, can be lost; design §6.8); a marker file flags an unfinished run; interrupted runs are repaired and listed in the library (the run being recorded is never taken for an interrupted one, and a run that stopped with an error is repaired and listed in the same launch, NFR-REL-02). If the run's folder is moved or deleted during the run (Files app), the run stops with a message. | P5 | Planned |
| FR-RUN-06 | Optional automatic stop after a set time or number of analyzed frames. | P5 | Planned |
| FR-RUN-07 | A run can be renamed and given a note (line, layer, product), once it is finished (NFR-REL-02). | P5 | Planned |

### 5.11 Library and export (FR-LIB, FR-EXP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-LIB-01 | Runs list, newest first: date, duration, frames, samples, mean angle, spread, percent within ±20°; incomplete (recovered) runs marked. | P5 | Planned |
| FR-LIB-02 | Run screen: summary values with confidence intervals, histogram, rose, time series, settings used, quality summary, and a browser for saved frames with their overlays. | P5 | Planned |
| FR-LIB-03 | Share one file or all files of a finished run (AirDrop, Mail, OneDrive …; NFR-REL-02); runs are visible in the Files app (*On My iPhone › Flake Scanner*). | P5 | Planned |
| FR-LIB-04 | Delete with confirmation, one or several finished runs (NFR-REL-02). | P5 | Planned |
| FR-LIB-05 | Re-analyze a run's saved frames with other parameters into a new result set. | P11 | Planned (backlog) |
| FR-EXP-01 | CSV files: header row with units in the column names, LF line ends, "." decimals, angles with 0.01° resolution, times as seconds from the run start plus ISO 8601 in `Run.json`. JSON: UTF-8, ISO 8601 dates, no non-finite numbers. | P5 | Planned |
| FR-EXP-02 | Files written by older builds stay readable (optional new fields, version numbers in `Run.json`). | P5 | Planned |

### 5.12 Remote link (FR-RMT)

Phone LiDAR's remote link (its FR-RMT-01…12) carried over and extended with the live preview, ROI drawing and settings.

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-RMT-01 | Both phones run the same app; each phone's role is *scanner*, *remote* or off, set from Home › **Connect to the other phone**. | P6 | Planned |
| FR-RMT-02 | Direct phone-to-phone Wi-Fi (no router or shared network), Bonjour service `_flakescan._tcp`. | P6 | Planned |
| FR-RMT-03 | Pairing with a 6-digit code shown on the scanner; the pairing is remembered (Keychain); one remote at a time. | P6 | Planned |
| FR-RMT-04 | The link is authenticated and encrypted (Phone LiDAR's CryptoKit handshake and channel). | P6 | Planned |
| FR-RMT-05 | The scanner keeps measuring and recording when the link drops; the remote reconnects by itself. | P6 | Planned |
| FR-RMT-06 | The remote shows the scanner's state: phase, run time, analyzed frames, achieved/requested rate, live statistics and histogram, MD state and angle, speed, quality light and reasons, conditions forecast (FR-QUAL-08), level, heat, battery and free storage. | P6 | Planned |
| FR-RMT-07 | Live preview on the remote: a downscaled picture (about 640 px, 2–5 fps) with the ROI and the analysis overlay, sent only while the remote shows it, never slowing the analysis (dropped when the link or the scanner is busy). | P6 | Planned |
| FR-RMT-08 | ROI drawing on the remote preview with the same gestures as on the scanner (FR-ROI-01); the scanner checks and applies it when no run is active and returns the applied ROI. | P6 | Planned |
| FR-RMT-09 | Remote controls: Start/Stop, analysis rate, method, exposure (mode, shutter, ISO, lock), focus (refocus, lock), torch, MD (Auto/Manual, detect again), target direction, limits, frame saving. The scanner validates every value and answers accepted or refused with the reason. Settings travel as patches of the changed fields only; when the two phones' settings schema versions differ, the remote shows the scanner read-only and asks to update the phone with the older build (design §6.14). | P6 | Planned |
| FR-RMT-10 | Copy finished runs from the scanner to the remote (list, resumable copy, import into the remote's library), as Phone LiDAR copies scans. | P6 | Planned |
| FR-RMT-11 | With the scanner role on, the scan screen stays open and ready after a run, so the remote can start the next one. | P6 | Planned |
| FR-RMT-12 | Snapshot from the remote (FR-RATE-05); its overlay picture comes to the remote as a downscaled preview-type message, which is allowed during a run like the live preview; the full-size snapshot files are copied with the run after Stop. | P6 | Planned |

