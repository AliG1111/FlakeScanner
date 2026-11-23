# Flake Scanner — Requirements

| | |
|---|---|
| Document | Functional and non-functional requirements, constraints, assumptions, open questions, traceability |
| Describes | The planned system (v1 = milestone M1, plus later phases). Nothing is implemented yet. |
| Date | 2026-11-23 |
| Companion documents | [design.md](design.md) (architecture, algorithms, formats, technology choices, risks), [implementation-plan.md](implementation-plan.md) (phases, model matrix, change log), [../CLAUDE.md](../CLAUDE.md) (agent rules), user guide [`../README.md`](../README.md) |

Requirements are written before the code. Each one carries the phase that delivers it and a status, so this file is also the traceability matrix (§9). Where a number is a proposed target it says so; the owner confirms or changes it (§8).

---

## 1. Purpose and scope

Flake Scanner is an iPhone app that watches the strands ("flakes") moving past on an OSB forming line and measures their **orientation**: the angle of each flake's long axis relative to the machine direction. It turns those angles into live and recorded statistics (mean angle, spread, alignment, percent within limits, histograms, trends) so the owner can judge and tune strand alignment. Accuracy has priority over speed.

A second iPhone running the same app can **control the scanner phone remotely** (pair, see a live picture, draw the analysis region, start and stop runs, change settings, read the statistics, copy the results), in the same way as the remote link of the owner's Phone LiDAR app.

The app is built, signed and distributed without a Mac, exactly like Phone LiDAR (GitHub Actions builds an `.ipa`; the owner installs it from Windows).

In scope for v1 (milestone M1):

| Area | Content |
|---|---|
| Live measurement | Camera above the moving mat; user-drawn region of interest (ROI); user-set analysis rate (shots per second); two measurement methods (*Flake edges*, *Edge orientation*) |
| Reference direction | Machine direction detected automatically from the material's movement, or set by hand |
| Statistics | Per frame and per run: count, mean angle, spread, alignment, orientation factor, percent within limits, histogram, rose, time series, confidence intervals |
| Measurement quality | Exposure, focus, motion blur, flicker banding, texture and level checks; failing frames excluded with a reason |
| Runs | Crash-safe recording of results (CSV/JSON) and optional frame images; library, charts, sharing, Files-app access |
| Remote link | Second iPhone: pairing, live preview, ROI drawing, start/stop, settings, live statistics, copy runs |
| Build | GitHub Actions, XcodeGen, unsigned `.ipa` (Sideloadly) and optional TestFlight, as Phone LiDAR |

Later phases (planned, not M1): LiDAR distance and tilt (millimetre scale, perspective correction), rolling-shutter and lens-distortion correction, flake length and width statistics, re-analysis of saved frames, a summary report image, a machine-learning per-flake method, a still-photo capture mode, alarms and trends, a Windows re-analysis script.

Out of scope: cloud services and internet use, outputs to plant systems (PLC, historian, OPC UA) in v1, Android, iPad layouts, several scanner phones in one run, App Store distribution.

## 2. Users and operating context

| Item | Description |
|---|---|
| Primary user | The owner: a controls and automation engineer in OSB manufacturing. Technical, comfortable with CSV/Excel and engineering units; not an iOS developer; works from a Windows PC. (Same user as Phone LiDAR.) |
| Scanner phone | iPhone 17 Pro Max (iOS 26), mounted above the forming line, camera pointing straight down at the mat, rigid vibration-isolated mount, USB-C power. Screen faces up, so the phone is hard to see and reach once mounted. |
| Remote phone | A second iPhone with the app (model to be confirmed, Q-06), held by the operator at a safe place near the line. It is the normal user interface while the scanner is mounted. |
| Material (assumed, Q-01, Q-03) | Loose strand mat on the forming belt after a forming head (face or core layer). Strands about 75–150 mm long and 10–25 mm wide, overlapping, partly hidden by each other. |
| Line (assumed, Q-02) | Mat speed 100–1,500 mm/s; camera 0.5–3 m above the mat (Phone LiDAR's line mount is 1–1.5 m). |
| Conditions | Dust, vibration, heat, plant lighting that may flicker, gloves, limited time and safe access at the mount. |
| Data consumers | The owner on Windows: Excel (CSV), own scripts (CSV, JSON, PNG frames). |

## 3. Use cases

| ID | Use case | Main flow | Requirements |
|---|---|---|---|
| UC-01 | Set up the scanner | Mount the phone › Home › Scan › level it (bubble) › check focus, exposure and the quality light › draw the ROI › wait until the machine direction shows *Detected* | FR-CAP, FR-ROI, FR-DIR, FR-QUAL, FR-CAL-01 |
| UC-02 | Set up from the second phone | Both phones › Home › Connect to the other phone › pair with the code › the remote shows the live picture › draw or adjust the ROI and settings from the remote | FR-RMT |
| UC-03 | Measure | Start run (scanner or remote) › live statistics and quality › Stop › run saved › summary | FR-RATE, FR-MEAS, FR-STAT, FR-RUN |
| UC-04 | Review a run | Runs › run › histogram, rose, time series, frames table, settings used, quality summary › share files | FR-LIB, FR-EXP |
| UC-05 | Snapshot | Snapshot (scanner or remote) › one full-resolution analysis with its overlay picture saved | FR-RATE-05, FR-RMT-12 |
| UC-06 | Copy runs to the remote | Remote › runs on the scanner › Copy › open on the remote | FR-RMT-10 |
| UC-07 | Check accuracy | Print the test target › place it under the camera (still or moving) › test-target mode compares measured and printed angles | FR-CAL-06, NFR-ACC-04 |
| UC-08 | Collect pictures | Turn on frame saving for a run › frames saved with the results (for tuning, audits and future ML training) | FR-RUN-03 |

## 4. Conventions

### 4.1 Angle convention

- **Flake angle θ**: the angle between a flake's long axis and the **machine direction (MD)**, the direction the mat travels, measured in the plane of the mat as seen from above. The camera looks down and its picture is not mirrored, so "as seen from above" equals "as seen in the picture".
- **Axial**: a flake has no head or tail, so θ and θ ± 180° are the same flake. Angles are reported in (−90°, +90°]. 0° = parallel to MD; ±90° = across the line (cross direction, CD).
- **Sign**: positive = counter-clockwise from MD as seen from above. The scan screen shows the MD arrow and a "+" arc so the sign can be read on the picture. Reversing the travel direction does not change any axial angle.
- **Target direction**: the orientation the layer should have (0° for face layers, 90° for core layers, or a custom value). "Deviation" = the smallest axial difference between θ and the target.

### 4.2 Statistics

For n samples with angles θᵢ (relative to MD) and weights wᵢ (1 for count-based statistics), using doubled angles because the data are axial:

| Name | Definition | Range / meaning |
|---|---|---|
| C, S | C = Σwᵢ cos 2θᵢ / Σwᵢ, S = Σwᵢ sin 2θᵢ / Σwᵢ | — |
| Mean angle θ̄ | ½ · atan2(S, C) | (−90°, 90°]; the mean axis |
| Alignment R | √(C² + S²) | 0 = no common direction … 1 = all parallel |
| Spread s (circular SD) | ½ · √(−2 ln R), in degrees | 0° = all parallel; grows without limit as R → 0 |
| Orientation factor f | C relative to the target direction: Σwᵢ cos 2(θᵢ − target) / Σwᵢ | +1 = all along the target, 0 = random, −1 = all across it |
| Mean absolute deviation | Σwᵢ ∣dev(θᵢ)∣ / Σwᵢ | degrees from the target |
| Percent within ±a | 100 · Σwᵢ [∣dev(θᵢ)∣ ≤ a] / Σwᵢ, default a = 10°, 20°, 30° | % |
| Histogram | Counts (or weights) in bins over (−90°, 90°], internally 1°, shown as 5° by default | — |

Statistics are shown as "—" until n reaches the minimum sample count (FR-STAT-07).

### 4.3 Other conventions

- Units: angles in degrees; picture sizes in pixels (px); lengths in mm and speeds in mm/s once the scale is known (shown with m/min and ft/min, lengths with inches); time in seconds. Files use "." as the decimal separator and never localized numbers.
- "Frame" = one camera image. "Analyzed frame" ("shot") = a frame chosen at the analysis rate and measured. "Run" = one Start…Stop recording of results. "Sample" = one measured angle (one flake edge, or one point of the orientation field).
- IDs are stable: `FR-<group>-<nn>`, `NFR-<group>-<nn>`. New requirements take the next free number; withdrawn ones keep their ID with status *Withdrawn*.
- Phase = the implementation-plan phase that delivers the requirement (P0–P11, [implementation-plan.md §6](implementation-plan.md#6-phased-checklists)).
- Status values: **Planned**; **Implemented** (on `main`, CI green, behaviour confirmed by code inspection and simulator tests); **Implemented – not verified on device** (needs the iPhone or its camera); **Verified** (on-device validation recorded in P8); **Withdrawn**.

## 5. Functional requirements

### 5.1 App shell (FR-APP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-APP-01 | Home offers **Scan** (scanner), **Connect to the other phone** (remote link), **Runs** (library) and **Settings / About** (version, build number, documentation links). | P0, P4 | Planned |
| FR-APP-02 | Portrait layout. The scan screen matches a phone mounted screen-up above the line, like Phone LiDAR's Line scan screen. | P4 | Planned |
| FR-APP-03 | The screen stays awake while the scan screen is open and while the scanner role is on. | P4, P6 | Planned |
| FR-APP-04 | Camera permission: a clear explanation before the system prompt, and a message with a link to Settings when it was denied. | P3 | Planned |
| FR-APP-05 | Settings persist between launches and can be reset to defaults; every run records the settings it used (FR-RUN-02). | P4 | Planned |

### 5.2 Capture (FR-CAP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-CAP-01 | Capture uses one fixed physical back camera: the 1× main (wide) camera by default, the telephoto as an option. Virtual multi-camera devices are never used, so the lens cannot switch during a run. | P3 | Planned |
| FR-CAP-02 | The capture format is chosen for accuracy: the highest resolution that runs at ≥ 30 fps, preferring formats with the highest maximum frame rate at that resolution (shortest sensor readout, design §6.12). The user can pick 1080p, 4K or 4:3 12 MP where the camera offers them. | P3 | Planned |
| FR-CAP-03 | Video stabilization is off; geometric distortion correction is on where supported; per-frame camera intrinsics are delivered where supported. | P3 | Planned |
| FR-CAP-04 | Exposure modes: **Auto, shutter-limited** (default; the longest allowed shutter follows the motion-blur budget, FR-QUAL-03) and **Manual** (shutter and ISO). Exposure is locked at Start for the whole run (default on). | P3 | Planned |
| FR-CAP-05 | Focus: autofocus on the ROI, then locked (default); tap to refocus; manual lens position. Focus stays locked during a run. | P3 | Planned |
| FR-CAP-06 | White balance is locked at Start. | P3 | Planned |
| FR-CAP-07 | Optional torch with a level setting (off by default), with a heat warning. | P3 | Planned |
| FR-CAP-08 | Live picture with overlays: ROI box, MD arrow and "+" arc, and the last analysis (detected edges coloured by angle, or orientation-field marks) refreshed at ≤ 5 fps. | P4 | Planned |
| FR-CAP-09 | Frames are processed in the sensor's native orientation; the mapping between the screen, the remote preview and the frame is exact (ROI kept in normalized frame coordinates). | P3 | Planned |
| FR-CAP-10 | Interruptions (app in background, call, camera error, system pressure) stop and save a running run; the camera restarts when possible; the screen says what happened. | P3, P5 | Planned |

### 5.3 Region of interest (FR-ROI)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-ROI-01 | The user defines the field of interest by dragging a box on the live picture, on the scanner and on the remote: drag on empty picture to draw a new box, drag inside to move it, drag the corner and edge handles to resize it. | P4, P6 | Planned |
| FR-ROI-02 | Only the ROI is analyzed. The ROI is stored in normalized frame coordinates, persisted with the settings and recorded in every run. | P1, P4 | Planned |
| FR-ROI-03 | The ROI stays inside the frame with a margin for the filters, and has a minimum size (default 256 × 256 px, and at least 2 × the expected flake length when known). The screen shows its size in px (and mm when the scale is known) and the expected number of samples per frame. | P4 | Planned |
| FR-ROI-04 | The ROI is locked while a run is active; a change is applied at the next Start. | P4 | Planned |
| FR-ROI-05 | Default ROI: the central 60 % × 60 % of the frame. | P4 | Planned |
| FR-ROI-06 | Exclusion masks (for belt edges, side walls, fixed objects). | P11 | Planned (backlog) |

### 5.4 Analysis rate (FR-RATE)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-RATE-01 | The user sets the analysis rate in shots per second: 0.1–10 /s in steps of 0.1 below 1 /s and 1 above, capped at the camera frame rate; default 2 /s. | P3, P4 | Planned |
| FR-RATE-02 | Accuracy before speed: frames are picked by timestamp at the set rate; analysis never lowers resolution or quality to keep up. When the analysis of a frame takes longer than the interval, the due frames are skipped (never queued) and the achieved rate is shown next to the requested rate. | P3 | Planned |
| FR-RATE-03 | Coverage: from the measured speed and the ROI length along MD the screen shows the share of passing material that is analyzed and the overlap between consecutive shots, and suggests the rate without overlap. | P4 | Planned |
| FR-RATE-04 | Analysis pauses while the line is stopped (no movement detected), so standing material is not counted again (on by default). | P3 | Planned |
| FR-RATE-05 | **Snapshot**: one analysis on demand that also saves the frame and its overlay picture. | P4, P5 | Planned |

### 5.5 Machine direction and speed (FR-DIR)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-DIR-01 | **Auto** (default): MD is measured from the frame-to-frame movement of the material (two-dimensional image registration) and averaged; the screen shows the MD angle relative to the picture axis, its uncertainty and *Detected* when it is stable. | P2, P3 | Planned |
| FR-DIR-02 | **Manual**: the user draws a line along the travel (for example along a side wall) or types the angle. | P4 | Planned |
| FR-DIR-03 | A run cannot start until MD is detected (Auto) or set (Manual); the remote gets the same reason. | P4, P6 | Planned |
| FR-DIR-04 | MD is fixed for a run and recorded with it. During the run the movement direction is still measured; a change of more than 0.5° (camera bumped, configurable) raises a warning and is recorded. | P3, P5 | Planned |
| FR-DIR-05 | Speed in px/s per frame and live; in mm/s (and m/min, ft/min) when the scale is known (FR-CAL-02). | P3 | Planned |

### 5.6 Measurement methods (FR-MEAS)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-MEAS-01 | **Flake edges** (default): straight flake edges are detected with sub-pixel orientation; each edge at least the minimum length long (default 1.5 × the expected flake width) is one sample with angle, length, centre and contrast. Collinear pieces of one edge interrupted by crossing flakes are merged before counting (design §6.5). Statistics are count-based (one sample per edge) or, by choice, length-weighted. | P2 | Planned |
| FR-MEAS-02 | **Edge orientation**: a structure-tensor orientation field is sampled on a grid over the ROI; samples are weighted by coherence × edge strength. Reported as the orientation distribution of flake edges and grain (its spread is not a per-flake spread, design §6.4). | P1 | Planned |
| FR-MEAS-03 | **Both**: both methods on the same frame for comparison; the headline numbers use the method chosen as primary. | P2, P4 | Planned |
| FR-MEAS-04 | Method parameters with defaults and an *Advanced* section: expected flake width (px, or mm with a scale), minimum edge length, integration scale, coherence and contrast thresholds, row normalization (Off / Auto / On). All are recorded in each run. | P1, P2, P4 | Planned |
| FR-MEAS-05 | Results are deterministic: the same frame, parameters and build give identical results, so saved frames can be re-analyzed reproducibly. | P1, P2 | Planned |
| FR-MEAS-06 | **Flakes (ML)**: per-flake instance segmentation with length and width, trained on the owner's pictures. | P10 | Planned (later) |

### 5.7 Statistics (FR-STAT)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-STAT-01 | Per analyzed frame: n, mean angle, alignment R, spread, orientation factor, mean absolute deviation, percent within ±10/20/30° (limits configurable), quality flags. | P1, P3 | Planned |
| FR-STAT-02 | Per run, over the included frames: the same values plus the histogram (5° bins, 1/2/10° selectable), a rose plot, the 95 % confidence interval of the mean angle and of the percent within ±20° (computed from the variation between frames, design §6.6), and frames included and excluded with reasons. | P1, P4, P5 | Planned |
| FR-STAT-03 | Rolling statistics over the last 10 s or 60 s (selectable) and time-series charts of mean angle, spread and percent within ±20° during and after a run. | P4, P5 | Planned |
| FR-STAT-04 | Target direction (0°, 90° or custom): deviation, orientation factor and percent-within values are relative to it. | P1, P4 | Planned |
| FR-STAT-05 | All statistics use the axial formulas of §4.2; histograms cover (−90°, 90°]. | P1 | Planned |
| FR-STAT-06 | Live values update at ≤ 4 Hz in fixed-width cells with fixed decimals (angles 0.1°, percentages 0.1 %). | P4 | Planned |
| FR-STAT-07 | Minimum sample count before statistics are shown: default 30 samples per frame for frame values and 200 per run for run values. | P1, P4 | Planned |

### 5.8 Measurement quality (FR-QUAL)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-QUAL-01 | Exposure: share of ROI pixels clipped dark or bright; warning above 1 %, frame excluded above 5 % (configurable). | P1, P3 | Planned |
| FR-QUAL-02 | Focus: sharpness of the ROI compared with the value at focus lock; warning when it drops by more than 30 %. | P1, P3 | Planned |
| FR-QUAL-03 | Motion blur budget: blur (px) = speed (px/s) × exposure time (s). Warning above 1.0 px, frame excluded above 2.0 px (configurable). In Auto exposure the longest shutter = budget / speed. | P1, P3 | Planned |
| FR-QUAL-04 | Flicker banding (lighting flicker with the rolling shutter): detected from the row profile of the ROI; warning when found; row normalization applied automatically in *Auto* (FR-MEAS-04). | P1, P3 | Planned |
| FR-QUAL-05 | Texture: too few samples or too little edge strength excludes the frame ("no texture"). | P1 | Planned |
| FR-QUAL-06 | Level: warning when the camera axis is more than 3° from vertical (gravity, FR-CAL-01). | P3 | Planned |
| FR-QUAL-07 | A quality light (green / amber / red) with the reasons on the scanner and the remote; each frame's quality values and flags are saved, and exclusions are counted by reason in the run summary. | P4, P5 | Planned |

### 5.9 Calibration and setup (FR-CAL)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-CAL-01 | Bubble level from gravity, with zero and reset (as Phone LiDAR). | P3 | Planned |
| FR-CAL-02 | Scale (optional): the camera distance to the mat is entered (mm) and combined with the camera intrinsics to give mm per px; without it, sizes and speeds stay in px. | P3 | Planned |
| FR-CAL-03 | LiDAR distance and surface tilt: measured scale and a perspective correction of the analysis. | P9 | Planned (later) |
| FR-CAL-04 | Rolling-shutter readout calibration and correction. | P9 | Planned (later) |
| FR-CAL-05 | Lens-distortion correction from the camera's calibration data. | P9 | Planned (later) |
| FR-CAL-06 | Test-target mode: a printable target (PDF in the repository) with flakes at known angles; the app compares the measured and the printed distribution (mean, spread, per-angle bias). | P8 | Planned |

### 5.10 Runs and recording (FR-RUN)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-RUN-01 | Start and Stop on the scanner and from the remote; states: *not ready* (with the reason), *ready*, *running*, *saving*, *failed*. | P4 | Planned |
| FR-RUN-02 | Each run is a folder `run_<yyyy-MM-dd_HHmmss>` with `Run.json` (settings, camera state, calibration, MD, app version; written at Start and completed at Stop), `Frames.csv` (one row per analyzed frame), `Samples.csv` (one row per sample, Flake edges) or `FrameHistograms.csv` (Edge orientation), `Histogram.csv` and `Summary.json` / `Summary.csv`. Formats in design §7. | P5 | Planned |
| FR-RUN-03 | Optional frame saving: every Nth analyzed frame's ROI as a lossless 8-bit PNG, optionally the full frame (HEIC) and the overlay picture; the screen shows the expected storage per minute. | P5 | Planned |
| FR-RUN-04 | Free space: Start is refused below 1 GB; a run stops and saves below 300 MB. | P5 | Planned |
| FR-RUN-05 | Crash safety: results are streamed to disk during the run; a marker file flags an unfinished run; interrupted runs are repaired and listed in the library. | P5 | Planned |
| FR-RUN-06 | Optional automatic stop after a set time or number of analyzed frames. | P5 | Planned |
| FR-RUN-07 | A run can be renamed and given a note (line, layer, product). | P5 | Planned |

### 5.11 Library and export (FR-LIB, FR-EXP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-LIB-01 | Runs list, newest first: date, duration, frames, samples, mean angle, spread, percent within ±20°; incomplete (recovered) runs marked. | P5 | Planned |
| FR-LIB-02 | Run screen: summary values with confidence intervals, histogram, rose, time series, settings used, quality summary, and a browser for saved frames with their overlays. | P5 | Planned |
| FR-LIB-03 | Share one file or all files of a run (AirDrop, Mail, OneDrive …); runs are visible in the Files app (*On My iPhone › Flake Scanner*). | P5 | Planned |
| FR-LIB-04 | Delete with confirmation, one or several runs. | P5 | Planned |
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
| FR-RMT-06 | The remote shows the scanner's state: phase, run time, analyzed frames, achieved/requested rate, live statistics and histogram, MD state and angle, speed, quality light and reasons, level, heat, battery and free storage. | P6 | Planned |
| FR-RMT-07 | Live preview on the remote: a downscaled picture (about 640 px, 2–5 fps) with the ROI and the analysis overlay, sent only while the remote shows it, never slowing the analysis (dropped when the link or the scanner is busy). | P6 | Planned |
| FR-RMT-08 | ROI drawing on the remote preview with the same gestures as on the scanner (FR-ROI-01); the scanner checks and applies it when no run is active and returns the applied ROI. | P6 | Planned |
| FR-RMT-09 | Remote controls: Start/Stop, analysis rate, method, exposure (mode, shutter, ISO, lock), focus (refocus, lock), torch, MD (Auto/Manual, detect again), target direction, limits, frame saving. The scanner validates every value and answers accepted or refused with the reason. | P6 | Planned |
| FR-RMT-10 | Copy runs from the scanner to the remote (list, resumable copy, import into the remote's library), as Phone LiDAR copies scans. | P6 | Planned |
| FR-RMT-11 | With the scanner role on, the scan screen stays open and ready after a run, so the remote can start the next one. | P6 | Planned |
| FR-RMT-12 | Snapshot from the remote (FR-RATE-05); the overlay picture can be viewed on the remote. | P6 | Planned |

## 6. Non-functional requirements

Status values as in §4.3. Targets marked *proposed* are first values for the owner to confirm (Q-05); the P8 validation measures them on the device.

### 6.1 Platform (NFR-PLAT)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-PLAT-01 | iPhone only, deployment target iOS 17.0; scanner role on the iPhone 17 Pro Max (iOS 26); remote role on any iPhone with iOS 17 or later. | `project.yml` deployment target and device family. | P0 | Planned |
| NFR-PLAT-02 | Native Swift with SwiftUI and Observation; Apple frameworks only (AVFoundation, Accelerate, CoreMotion, Network, CryptoKit, Charts, ImageIO); no third-party packages without a design decision. | No package dependencies in `project.yml`. | P0 | Planned |

### 6.2 Measurement accuracy (NFR-ACC)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-ACC-01 | Rotation invariance of the estimators. | Synthetic straight edges and gratings at every angle 0–179° in 1° steps: bias ≤ 0.1° (Flake edges, edges ≥ 50 px long) and ≤ 0.2° (Edge orientation). Unit tests in CI. | P1, P2 | Planned |
| NFR-ACC-02 | Accuracy on synthetic mats with a known distribution (fixed seeds; design §6.13). | Mean angle error ≤ 0.5° for any true mean direction (both methods). Flake edges, face-layer alignment (spread ≤ 16°): spread error ≤ 1.0° and percent-within-±20° error ≤ 3 points; the lab prototype is at the limit (−0.3…−1.0°, +0.4…+3.1 points). Weaker alignment (spread 16–40°): the prototype under-reads the spread by 1.2–2.0° (percent within ±20° 3–5 points high), more in very dense mats, because crossing flakes hide each other; P2 must cut this to ≤ 1.0° / ≤ 3 points or record the residual as a documented bias. Unit tests in CI. | P1, P2 | Planned |
| NFR-ACC-03 | Machine-direction accuracy. | Synthetic moving sequences: MD error ≤ 0.1°. Device: ≤ 0.3° against a reference line (P8). | P2, P8 | Planned |
| NFR-ACC-04 | End-to-end accuracy on the device with the printed test target, still and moving, under the plant lighting. | Proposed: mean angle within ±0.5°, spread within ±1.0°, percent within ±20° within ±3 points (P8). | P8 | Planned |
| NFR-ACC-05 | Motion blur control. | Default budget 1.0 px; frames above the exclusion limit (2.0 px) never enter the statistics (FR-QUAL-03). | P3 | Planned |
| NFR-ACC-06 | Mount tilt. | ≤ 3° from vertical keeps the perspective bias of the mean angle ≤ 0.1° when the ROI is centred in the picture (local errors toward the picture edge are larger, design §6.12); the level warns above 3° and the scan screen hints when the ROI is off-centre. | P3, P4 | Planned |
| NFR-ACC-07 | Rolling shutter. | With the travel along the sensor readout direction (default mount, design §6.12) the mean angle is unbiased and the spread changes by less than 2 % at 1,500 mm/s, assuming a readout time ≤ 8 ms (measured in P8 V3); documented until corrected (FR-CAL-04). | P3, P9 | Planned |
| NFR-ACC-08 | Statistical precision is visible. | Run screen and `Summary.json` show the 95 % confidence intervals; a run of 100 non-overlapping shots typically reaches ±0.5° on the mean angle (informational). | P5 | Planned |

### 6.3 Performance (NFR-PERF)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-PERF-01 | Capture keeps its frame rate while analysis runs; analysis has its own queue; no unbounded queues; camera buffers are released quickly (the ROI is copied out). | No drop in capture rate with analysis on (P8 V1). | P3 | Planned |
| NFR-PERF-02 | Analysis time per shot on the iPhone 17 Pro Max for a 2,000 × 2,000 px ROI. | Proposed: ≤ 150 ms (Edge orientation), ≤ 300 ms (Flake edges), so ≥ 3 shots/s at that ROI (P8 V2). | P1, P2, P8 | Planned |
| NFR-PERF-03 | Responsive UI. | Live values ≤ 4 Hz, overlay ≤ 5 fps, no main-thread work longer than 16 ms per update. | P4 | Planned |
| NFR-PERF-04 | Remote link. | Status 4 Hz; preview 2–5 fps at about 640 px; command answer ≤ 1 s at 5 m line of sight (P8). | P6 | Planned |
| NFR-PERF-05 | Sustained runs on USB-C power. | 60-minute run without thermal shutdown. At *serious* thermal state preview and overlay slow down and the analysis rate may be capped with a visible notice; at *critical* the run stops and saves (P8). | P3, P5 | Planned |

### 6.4 Reliability and data integrity (NFR-REL)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-REL-01 | A crash, kill or interruption during a run leaves a recoverable run; captured data is never deleted on failure. | Kill test (P8); unit tests of repair. | P5 | Planned |
| NFR-REL-02 | Metadata files are written atomically; a run appears in the library only when its `Run.json` exists. | Code inspection. | P5 | Planned |
| NFR-REL-03 | The remote link cannot harm a run: own queue, never blocks capture or analysis, no file sends while a run is active. | Code inspection; P8. | P6 | Planned |
| NFR-REL-04 | Reproducibility: every run records the app version and build, all parameters and the camera settings actually applied (format, exposure, ISO, lens position, intrinsics, MD). | `Run.json` content. | P5 | Planned |

### 6.5 Storage and memory (NFR-STO)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-STO-01 | Data stored locally under the app's `Documents`, visible in the Files app. | Code inspection. | P5 | Planned |
| NFR-STO-02 | Bounded memory: analysis buffers are reused; memory does not grow with run length; samples are streamed to disk. | Instruments / memory gauge in a 60-minute run (P8). | P1, P5 | Planned |
| NFR-STO-03 | Data volume shown before Start (results per minute, frame images per minute). | Code inspection. | P5 | Planned |

### 6.6 Usability (NFR-USE)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-USE-01 | Usable with gloves and at arm's length: primary actions ≥ 44 × 44 pt, readouts on dark panels over the picture. | Owner check (P8). | P4 | Planned |
| NFR-USE-02 | The remote alone is enough for normal operation: setup, ROI, runs, results. | Owner check (P8). | P6 | Planned |
| NFR-USE-03 | Validity is always visible: quality light with reasons, "—" for values without enough samples. | Code inspection. | P4 | Planned |
| NFR-USE-04 | Units as §4.3; metric first with imperial alongside. | Code inspection. | P4 | Planned |
| NFR-USE-05 | Screens fit any text size; readouts keep fixed places and shrink instead of wrapping (Phone LiDAR NFR-USE-06 pattern). | Owner check. | P4 | Planned |

### 6.7 Maintainability and testability (NFR-MNT, NFR-TST)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-MNT-01 | Warning-free build; one folder per module; pure logic separated from device code; doc comments on non-obvious maths; units in names or comments. | CI: 0 warnings. | P0 | Planned |
| NFR-MNT-02 | Requirements, design, plan with change log, `CLAUDE.md` and the user guide stay current with every change. | Definition of done in the plan. | All | Planned |
| NFR-TST-01 | Pure logic (statistics, estimators, MD estimation, quality metrics, scheduler, formats, remote protocol and crypto) is unit-tested in a host-less XCTest bundle on the iOS Simulator; CI runs it for every pull request. | CI `unit-tests` green. | P0–P6 | Planned |
| NFR-TST-02 | Golden tests: synthetic images from fixed seeds with expected statistics, cross-checked against the Python lab (`tools/lab`). | Tests in CI. | P1, P2 | Planned |
| NFR-TST-03 | On-device behaviour and accuracy are validated with documented procedures and recorded results. | P8 records. | P8 | Planned |

### 6.8 Security and privacy (NFR-SEC)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-SEC-01 | Only the permissions used: camera, Local Network (`NSBonjourServices` = `_flakescan._tcp`), photo-library add for the share sheet. No microphone, location or photo-library read. | `Info.plist`. | P0, P6 | Planned |
| NFR-SEC-02 | Local only: no internet services, analytics or accounts; the only network use is the remote link to the one paired phone. | Network code only in `Remote/`. | P6 | Planned |
| NFR-SEC-03 | Repository hygiene: no secrets, Apple IDs, keys, certificates, profiles, personal data, plant pictures or run data in git. | `.gitignore`, review. | P0 | Planned |
| NFR-SEC-04 | Remote link security as Phone LiDAR NFR-SEC-06, including its documented pairing limitation (design §10.10). | Code review; unit tests. | P6 | Planned |
| NFR-SEC-05 | Values from the other phone are untrusted: sizes, ROI bounds and every parameter range are checked; no crash on bad peer input. | Unit tests. | P6 | Planned |
| NFR-SEC-06 | CI least privilege: read-only token, pinned actions and tools, secrets only in the TestFlight steps. | Workflow review. | P0 | Planned |

### 6.9 Build and distribution (NFR-BLD)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-BLD-01 | Builds run on GitHub Actions (`macos-26`, Xcode 26.x); XcodeGen generates the project; no `.xcodeproj` in git; build number = workflow run number. | Workflow `Build iOS app`. | P0 | Planned |
| NFR-BLD-02 | Unsigned `.ipa` artifact for Sideloadly; optional TestFlight job (four secrets, as Phone LiDAR). | Artifacts on each run. | P0 | Planned |
| NFR-BLD-03 | CI diagnostics: errors, warning count and failed tests on the run summary; logs kept as artifacts. | Run summary. | P0 | Planned |
| NFR-BLD-04 | Bundle ID `ca.gervais.flakescanner`, distinct from Phone LiDAR, so both apps install side by side. | `project.yml`. | P0 | Planned |

## 7. Constraints and assumptions

| ID | Constraint / assumption |
|---|---|
| CON-01 | No Mac; no local Swift toolchain. GitHub Actions is the only compiler. Algorithms can be prototyped in Python in the cloud workspace (`tools/lab`). |
| CON-02 | Camera, LiDAR and the remote radio work only on physical iPhones; the simulator runs pure logic only. |
| CON-03 | The Xcode project is generated by XcodeGen; `project.yml` is the source of truth. |
| CON-04 | Distribution without the App Store: Sideloadly with a free Apple ID (7-day signing, 3 apps) or TestFlight with the paid program. |
| CON-05 | Builds stay warning-free. |
| CON-06 | Accuracy has priority over speed (owner, 2026-11-23). |
| CON-07 | If the repository is public (recommended for free macOS build minutes), nothing secret, personal or from the plant (pictures, runs) is committed. |
| ASM-01 | The camera looks straight down (within 3°) at the mat surface; the mat moves as a rigid body in a straight line (belt). |
| ASM-02 | Flakes are elongated (length/width ≥ 3) with straight long edges; the visible top layer represents the layer's orientation. |
| ASM-03 | Line speed 100–1,500 mm/s, camera height 0.5–3 m, strands 75–150 × 10–25 mm (to be confirmed, Q-01…Q-03). |
| ASM-04 | Enough light for exposures of 1/2,000 s or shorter at ISO ≤ 1,600; a flicker-free supplementary light may be needed (Q-04). |
| ASM-05 | "The Lidar app" in the owner's request is Phone LiDAR; its remote link (pairing code, direct Wi-Fi, auto-reconnect, copy) is the model, extended with a live preview so the ROI can be drawn on the remote (Q-07). |

## 8. Open questions

| ID | Question | Why it matters | Default until answered |
|---|---|---|---|
| Q-01 | Where will the camera look: the mat surface on the belt after which forming head, face or core layer? (Or strands falling from the orienter?) | Target direction, lighting, expected alignment, whether flakes are on a surface. | Mat surface on the belt; target 0° (face layer), selectable. |
| Q-02 | Line speed range and the possible camera height above the mat. | Shutter (blur), analysis rate, coverage, resolution. | 100–1,500 mm/s; 0.5–3 m. |
| Q-03 | Typical strand length and width; how regular are the edges? | Default flake width, minimum edge length, ROI size. | 75–150 × 10–25 mm. |
| Q-04 | Lighting at the mount (LED, metal halide, fluorescent?). Can a flicker-free LED light be added? | Flicker banding and shadows bias angles (design §6.13). | Banding detection and row normalization on *Auto*. |
| Q-05 | Which statistics do you report today (mean angle, % within ±20° or ±30°, orientation index…), and is there a reference method to compare with (hand measurement on photos, a commercial system)? | Headline numbers, accuracy targets, validation. | §4.2 set; targets in §6.2. |
| Q-06 | Model and iOS version of the second iPhone. | Deployment target for the remote role. | iOS 17 or later. |
| Q-07 | Is "the Lidar app" your Phone LiDAR app? | Reuse of its remote link. | Yes (ASM-05). |
| Q-08 | GitHub repository for this app (name, public or private). This session cannot create it. | CI is the only compiler. | `FlakeScanner`, public like Phone LiDAR. |
| Q-09 | A 30–60 s video and a few photos of the mat from the intended mount position (kept out of the public repository). | Tuning and validating the methods on real flakes. | Synthetic images only. |
| Q-10 | Install with Sideloadly (free, 7 days) or TestFlight (paid), as for Phone LiDAR? | Re-signing effort on the plant floor. | Same as Phone LiDAR. |

## 9. Traceability

Each requirement row above names its phase; the implementation plan names the requirements of each task. Status moves from *Planned* to *Implemented* at merge and to *Verified* when the P8 test that covers it is recorded.

| Group | Design sections | Plan phases | Tests |
|---|---|---|---|
| FR-APP | §3.1 | P0, P3, P4 | UI check (P8) |
| FR-CAP | §3.2, §5, §6.10–6.12 | P3 | Device (P8 V1, V3) |
| FR-ROI | §3.6, §6.1 | P1, P4, P6 | Unit (mapping), device |
| FR-RATE | §6.9, §6.11 | P3, P4 | Unit (scheduler, coverage) |
| FR-DIR | §6.8 | P2, P3, P4 | Unit (synthetic motion), device (P8 V4) |
| FR-MEAS | §6.2–6.5 | P1, P2 | Unit (golden, invariance), device (P8 V5) |
| FR-STAT | §6.6, §6.7 | P1, P4, P5 | Unit |
| FR-QUAL | §6.10 | P1, P3 | Unit (synthetic blur, banding), device |
| FR-CAL | §6.12 | P3, P8, P9 | Device |
| FR-RUN, FR-LIB, FR-EXP | §7, §8, §9 | P5 | Unit (formats, repair), device |
| FR-RMT | §3.7, §6.14, §10.10 | P6 | Unit (protocol, crypto, loopback), device (P8 V8) |

## 10. Document history

| Date | Change |
|---|---|
| 2026-11-23 | First version: requirements for v1 (M1) and later phases, from the owner's request (flake angle statistics, remote control like Phone LiDAR, accuracy over speed with a user-set shot rate, ROI drawn by dragging a box) and Phone LiDAR's operating context. |
