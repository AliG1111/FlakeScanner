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
| Live measurement | Camera directly above the moving mat, its distance measured by the LiDAR (millimetre scale); user-drawn region of interest (ROI); user-set analysis rate (shots per second); two measurement methods (*Flake edges*, *Edge orientation*) |
| Reference direction | Machine direction detected automatically from the material's movement, or set by hand |
| Statistics | Per frame and per run: count, mean angle, spread, alignment, orientation factor, percent within limits, histogram, rose, time series, confidence intervals |
| Measurement quality | Exposure, focus, motion blur, flicker banding, texture and level checks; failing frames excluded with a reason |
| Runs | Crash-safe recording of results (CSV/JSON) and optional frame images; library, charts, sharing, Files-app access |
| Remote link | Second iPhone: pairing, live preview, ROI drawing, start/stop, settings, live statistics, copy runs |
| Build | GitHub Actions, XcodeGen, unsigned `.ipa` (Sideloadly) and optional TestFlight, as Phone LiDAR |

Later phases (planned, not M1): LiDAR surface tilt (perspective correction), rolling-shutter and lens-distortion correction, flake length and width statistics, re-analysis of saved frames, a summary report image, a machine-learning per-flake method, a still-photo capture mode, alarms and trends, a Windows re-analysis script.

Out of scope: cloud services and internet use, outputs to plant systems (PLC, historian, OPC UA) in v1, Android, iPad layouts, several scanner phones in one run, App Store distribution.

## 2. Users and operating context

| Item | Description |
|---|---|
| Primary user | The owner: an engineer at an OSB mill. Technical, comfortable with CSV/Excel and engineering units; not an iOS developer; works from a Windows PC. (Same user as Phone LiDAR.) |
| Scanner phone | iPhone 17 Pro Max (iOS 26) with LiDAR, which measures the camera distance (FR-CAL-02; the owner confirms the scanner phone will have one), mounted above the forming line, camera pointing straight down at the mat, rigid vibration-isolated mount, USB-C power. Screen faces up, so the phone is hard to see and reach once mounted. |
| Remote phone | A second iPhone with the app (model to be confirmed, Q-06), held by the operator at a safe place near the line. It is the normal user interface while the scanner is mounted. |
| Material (assumed, Q-01, Q-03) | Loose strand mat on the forming belt after a forming head (face or core layer). Strands about 75–150 mm long and 10–25 mm wide, overlapping, partly hidden by each other. |
| Line (Q-02) | Camera directly over the line, looking down; mat speed 100–1,000 mm/s (owner, 2026-11-23). The camera height varies from mount to mount and is measured by the LiDAR (FR-CAL-02); assumed 0.5–3 m (Phone LiDAR's line mount is 1–1.5 m). |
| Conditions | Dust, vibration, heat, plant lighting that differs from location to location (Q-04) and may flicker, gloves, limited time and safe access at the mount. |
| Data consumers | The owner on Windows: Excel (CSV), own scripts (CSV, JSON, PNG frames). |

## 3. Use cases

| ID | Use case | Main flow | Requirements |
|---|---|---|---|
| UC-01 | Set up the scanner | Mount the phone › Home › Scan › level it (bubble) › check focus, exposure, the required shutter, the conditions forecast and the quality light › draw the ROI › measure the flake width › wait until the machine direction shows *Detected* | FR-CAP, FR-ROI, FR-DIR, FR-QUAL, FR-CAL-01, FR-CAL-07 |
| UC-02 | Set up from the second phone | Both phones › Home › Connect to the other phone › pair with the code › the remote shows the live picture › draw or adjust the ROI and settings from the remote | FR-RMT |
| UC-03 | Measure | Start run (scanner or remote) › live statistics and quality › Stop › run saved › summary | FR-RATE, FR-MEAS, FR-STAT, FR-RUN |
| UC-04 | Review a run | Runs › run › histogram, rose, time series, frames table, settings used, quality summary › share files | FR-LIB, FR-EXP |
| UC-05 | Snapshot | Snapshot (scanner or remote) › one full-resolution analysis with its overlay picture saved | FR-RATE-05, FR-RMT-12 |
| UC-06 | Copy runs to the remote | Remote › runs on the scanner › Copy › open on the remote | FR-RMT-10 |
| UC-07 | Check accuracy | Print the test target › place it under the camera (still, or taped to the moving belt) › Scan › Test target › the app finds the printed markers and reference bar › compares measured and printed angles (mean, spread, percent within ±20°, per-angle bias) | FR-CAL-06, NFR-ACC-04 |
| UC-08 | Collect pictures | Turn on frame saving for a run › frames saved with the results (for tuning, audits and future ML training) | FR-RUN-03 |
| UC-09 | Probe the phone and the plant | Settings › Diagnostics › camera report, sample frames with their camera data, light check and readout test, self-test › share the zip | FR-APP-06 |

## 4. Conventions

### 4.1 Angle convention

- **Flake angle θ**: the angle between a flake's long axis and the **machine direction (MD)**, the direction the mat travels, measured in the plane of the mat as seen from above. The camera looks down and its picture is not mirrored, so "as seen from above" equals "as seen in the picture".
- **Axial**: a flake has no head or tail, so θ and θ ± 180° are the same flake. Angles are reported in (−90°, +90°]. 0° = parallel to MD; ±90° = across the line (cross direction, CD).
- **Sign**: positive = counter-clockwise from MD as seen from above. The scan screen shows the MD arrow and a "+" arc so the sign can be read on the picture. Reversing the travel direction does not change any axial angle.
- **Target direction**: the orientation the layer should have (0° for face layers, 90° for core layers, or a custom value). "Deviation" dev = wrap(θ − target) to (−90°, 90°], the smallest signed axial difference between θ and the target.
- **Display range**: angles, means, histograms, rose plots and time series are shown in (target − 90°, target + 90°], so the target sits in the middle and a core layer (target 90°) never splits at the ±90° wrap. Files keep θ in (−90°, 90°] and carry the signed deviation next to it (`dev_deg`, `mean_dev_deg`), which can be averaged in a spreadsheet when the spread is small.

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
| Histogram | Counts (or weights) in bins of the deviation from the target over (−90°, 90°] (the same as θ bins when the target is 0°), internally 1°, shown as 5° by default | — |

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
| FR-APP-06 | **Diagnostics** (Settings › Diagnostics), because there is no Xcode console: (a) camera report: every back camera's formats with size, frame-rate range, binning, video HDR, distortion-correction and intrinsics-delivery support, exposure and ISO ranges, and the LiDAR depth camera's formats with depth delivery; (b) sample capture: a short burst at a chosen format with locked short exposure, saved as ROI-sized PNGs plus per-frame camera data (timestamps, exposure, ISO, lens position, intrinsics, gravity); (c) light check (flicker index, 50 or 60 Hz mains), readout-time test (two bursts, the second with the phone turned 180°, with plausibility checks, design §6.16) and the LiDAR distance reading (design §6.17); (d) self-test: the built-in synthetic fixture images run through the analysis and are compared with their stored results; (e) everything shared as one zip. Diagnostics files stay on the phone until shared and are never committed. | P0, P2 | Planned |

### 5.2 Capture (FR-CAP)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-CAP-01 | Capture uses one fixed physical back camera: the 1× main (wide) camera by default, the telephoto as an option. Virtual multi-camera devices are never used, so the lens cannot switch during a run. | P3 | Planned |
| FR-CAP-02 | The capture format is chosen for accuracy by ranking, not by hard filters: the highest resolution that runs at ≥ 30 fps, preferring formats that are not binned and have the highest maximum frame rate at that resolution (shortest sensor readout, design §6.12). A binned format is used only when no other meets the rate, and is flagged. The user can pick 1080p, 4K or 4:3 12 MP where the camera offers them. | P0, P2, P3 | Planned |
| FR-CAP-03 | Image processing is fixed for the whole run: video stabilization off; video HDR off (no automatic HDR); low-light boost off; a fixed frame duration (no automatic frame-rate changes); geometric distortion correction on where supported; per-frame camera intrinsics delivered where supported (the device probe confirms which image they describe, P0.8). Every applied state is recorded (NFR-REL-04). | P0, P3 | Planned |
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
| FR-RATE-02 | Accuracy before speed: frames are picked by timestamp at the set rate; analysis never lowers resolution or quality to keep up. When the analysis of a frame takes longer than the interval, the shots that fall due meanwhile are skipped (never queued, no catch-up burst); a busy analysis never shifts the schedule, so the mean time between shots is at most the longer of the interval and the analysis time, plus one frame interval; the due shots not taken are counted (not the time while the line is stopped) and the achieved rate (per second of moving time) is shown next to the requested rate (design §6.9). | P2, P3 | Planned |
| FR-RATE-03 | Coverage: from the measured speed and the ROI length along MD the screen shows the share of passing material that is analyzed and the overlap between consecutive shots, and suggests the rate without overlap. | P2, P4 | Planned |
| FR-RATE-04 | Analysis pauses while the line is stopped (no movement detected), so standing material is not counted again (on by default). | P2, P3 | Planned |
| FR-RATE-05 | **Snapshot**: one analysis on demand that also saves the frame and its overlay picture: inside the run's `Frames/` (flagged as a snapshot) during a run, otherwise in `Snapshots/` (design §7.2). | P4, P5 | Planned |

### 5.5 Machine direction and speed (FR-DIR)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-DIR-01 | **Auto** (default): MD is measured from the frame-to-frame movement of the material (two-dimensional image registration) and averaged; the screen shows the MD angle relative to the picture axis, its uncertainty and *Detected* when it is stable. | P2, P3 | Planned |
| FR-DIR-02 | **Manual**: the user draws a line along the travel (for example along a side wall) or types the angle. Angles of drawn lines and boxes are computed in pixel coordinates, never in normalized coordinates (which stretch differently along x and y). | P4 | Planned |
| FR-DIR-03 | A run cannot start until MD is detected (Auto) or set (Manual); the remote gets the same reason. | P4, P6 | Planned |
| FR-DIR-04 | MD is fixed for a run and recorded with it. During the run the movement direction is still measured. A confirmed change of more than 0.5° (camera bumped; 0.5° for ≥ 3 s, configurable) excludes the frames from the start of the change with the reason *MD changed* until the direction returns (shots enter the run statistics and files after a delay that covers the confirmation, design §6.8); if it has not returned after 10 s the run stops and saves with that reason, because every later angle would be offset. The event is recorded. | P2, P3, P5, P8 | Planned |
| FR-DIR-05 | Speed in px/s per frame and live; in mm/s (and m/min, ft/min) when the scale is known (FR-CAL-02). | P2, P3 | Planned |

### 5.6 Measurement methods (FR-MEAS)

| ID | Requirement | Phase | Status |
|---|---|---|---|
| FR-MEAS-01 | **Flake edges** (default): straight flake edges are detected with sub-pixel orientation; each edge at least the minimum length long (default 1.5 × the flake width of FR-CAL-07) is one sample with angle, length, centre and contrast. Collinear pieces of one edge interrupted by crossing flakes are merged before counting; edges cut by the ROI border are clipped to the ROI before the minimum length applies (design §6.5). Statistics are count-based (one sample per edge) or, by choice, length-weighted. | P2 | Planned |
| FR-MEAS-02 | **Edge orientation**: a structure-tensor orientation field is sampled on a grid over the ROI; samples are weighted by coherence × edge strength. Reported as the orientation distribution of flake edges and grain (its spread is not a per-flake spread, design §6.4). | P1 | Planned |
| FR-MEAS-03 | **Both**: both methods on the same frame for comparison; the headline numbers use the method chosen as primary. Files keep the methods apart: `Frames.csv` has one row per frame and method with a `method` column, `Samples.csv` holds the *Flake edges* samples and `FrameHistograms.csv` the *Edge orientation* histograms, and the summaries have one block per method (design §7). | P2, P4 | Planned |
| FR-MEAS-04 | Method parameters with defaults and an *Advanced* section: minimum edge length (default from the flake width, FR-CAL-07), integration scale, coherence and contrast thresholds, banding correction for *Edge orientation* (Off / Auto / On; *Auto* corrects only shots with strong bands, *Off* leaves them out, *On* corrects every shot, design §6.2). All are recorded in each run. | P1, P2, P4 | Planned |
| FR-MEAS-05 | Results are deterministic: the same frame, parameters and build give identical results, so saved frames can be re-analyzed reproducibly. | P1, P2 | Planned |
| FR-MEAS-06 | **Flakes (ML)**: per-flake instance segmentation with length and width, trained on the owner's pictures. | P10 | Planned (later) |

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
| FR-QUAL-03 | Motion blur budget: blur (px) = speed (px/s) × exposure time (s). Warning above 1.0 px, frame excluded above 2.0 px (configurable). In Auto exposure the longest shutter = budget / speed. Setup shows the shutter the budget needs (budget × mm/px ÷ speed, for example 1/2,800 s at 1,000 mm/s and 0.36 mm/px) and whether the light allows it at ISO ≤ 1,600. | P1, P2, P3 | Planned |
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
| FR-CAL-07 | **Flake width** (required setup, design §6.5): the typical flake width in px is set before the first run on a mount, by dragging across three to five typical flakes on a frozen frame (the app uses the second-widest, because a width set too narrow lets flake ends pass as edges and inflates the spread, while one set up to twice too wide costs little, lab E10) or from the nominal width in mm with the scale. Start is refused until it is set; it is recorded in every run. It is stored with the camera and format it was measured on, together with that format's focal length in px (fx, from the intrinsics or the field of view) and the camera distance (FR-CAL-02; the latest valid LiDAR reading on that camera when the width is set, taken then if Setup has none): a format change on the same camera rescales it by the ratio of fx, a new camera distance by the inverse ratio of the distances, and a camera change asks for a new measurement; when either distance is missing, Start asks to confirm the width or measure it again. An automatic estimate from paired flake edges warns when the setting is below 0.75 × or above 2 × the estimate (lab E10, E11; P2.1 improves the estimate and tunes the limits). Below 12 px per flake width the screen warns (move closer or use the telephoto). | P2, P4 | Planned |

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

## 6. Non-functional requirements

Status values as in §4.3. Targets marked *proposed* are first values for the owner to confirm (Q-05); the P8 validation measures them on the device.

### 6.1 Platform (NFR-PLAT)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-PLAT-01 | iPhone only, deployment target iOS 17.0; scanner role on the iPhone 17 Pro Max (iOS 26); remote role on any iPhone with iOS 17 or later. | `project.yml` deployment target and device family. | P0 | Implemented |
| NFR-PLAT-02 | Native Swift with SwiftUI and Observation; Apple frameworks only (AVFoundation, Accelerate, CoreMotion, Network, CryptoKit, Charts, ImageIO); no third-party packages without a design decision. | No package dependencies in `project.yml`. | P0 | Implemented |

### 6.2 Measurement accuracy (NFR-ACC)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-ACC-01 | Rotation invariance of the estimators. | Synthetic straight edges and gratings at every angle 0–179° in 1° steps: bias ≤ 0.1° (Flake edges, edges ≥ 50 px long) and ≤ 0.2° (Edge orientation). Unit tests in CI. | P1, P2 | Planned |
| NFR-ACC-02 | Accuracy on synthetic mats with a known distribution (seeded; design §6.13). Conditions: the lab's density (650 strands of 120 × 24 px ± 30 % per 768 × 768 px), aspect 5 : 1 to 10 : 1, flake width set to the true width, no blur, banding or shadow. Image counts are fixed in advance from the pooled per-image standard deviation of the lab results, so that the standard error (SE) of each mean error is at most a third of its tolerance; with about 1° per image for the mean at κ = 4 that is at least 36 images per condition (P1.6). | **Face-layer alignment** (spread about 15°, κ = 4, and tighter): mean angle error ≤ 0.5° for any true mean direction (both methods); *Flake edges* spread error ≤ 1.5° and percent-within-±20° error ≤ 4 points, goal 1.0° / 3 points. Lab prototype at κ = 4: spread −0.6…−1.1°, +1.9…+3.4 points (κ = 8: +0.1°, +0.3 points); mean errors within ±0.65° at SE 0.2–0.4° (the largest, *Edge orientation* +0.65° at 45° and −0.62° at κ = 8, to be settled in P1.6). **Weaker alignment** (spread about 24°, κ = 2): *Flake edges* mean ≤ 1.0°, spread ≤ 2.0°, percent within ±20° ≤ 5 points (prototype −0.8…+0.2°, −1.0…−1.4°, +2.2…+3.3 points); *Edge orientation* mean ≤ 1.5° (prototype −1.4…+1.6° at SE 0.6°). The *Edge orientation* spread is an edge spread, not a flake spread (FR-MEAS-02), and has no tolerance. Outside these conditions (spread above 30°, twice the lab density, blur, banding, one-sided light) the lab's biases are documented in design §6.12–6.13, not tested as limits. Unit tests in CI. | P1, P2 | Planned |
| NFR-ACC-03 | Machine-direction accuracy. | Synthetic moving sequences: MD error ≤ 0.1°. Device: ≤ 0.3° against the travel direction of the test target's markers on the moving belt (FR-CAL-06, design §6.15, P8). | P2, P8 | Planned |
| NFR-ACC-04 | End-to-end accuracy on the device with the printed test target (FR-CAL-06), still and moving, under the plant lighting. Still, the printed reference bar is the MD reference; on the belt the markers' track gives the travel direction and the taping angle (design §6.15). No hand-drawn line enters the result. | Proposed: mean angle within ±0.5°, spread within ±1.0°, percent within ±20° within ±3 points (P8). | P8, P9 | Planned |
| NFR-ACC-05 | Motion blur control. | Default budget 1.0 px; frames above the exclusion limit (2.0 px) never enter the statistics (FR-QUAL-03). | P2, P3 | Planned |
| NFR-ACC-06 | Mount tilt. | For an ROI centred in the picture, ≤ 3° of tilt keeps the perspective bias of the mean angle ≤ 0.1°. An ROI whose centre is off-centre by x̄ (in focal lengths; 0.2 is about a third of the way to the side) adds up to φ·x̄ for flakes perpendicular to the tilt axis: 0.6° at φ = 3°, 0.2° at 1° (design §6.12). The level is amber above 1° and red above 3° (FR-QUAL-06); the scan screen shows the tilt bias bound of the current ROI. | P3, P4 | Planned |
| NFR-ACC-07 | Rolling shutter. | With the travel along the sensor readout (default mount, design §6.12) each angle moves by about ∓(s/2)·sin 2θ, s = v·T_r / H (speed, readout time, picture extent along the readout in mm): the spread scales by (1 ∓ s) and a layer whose mean is μ from MD reads ∓(s/2)·sin 2μ off, so deviations from MD are about s too small or large. s ≈ 1.0 % at 1,000 mm/s, T_r = 8 ms and 1 m camera height (H ≈ 0.8 m), 2 % at 0.5 m. The app computes s = v_px·T_r / rows from the measured speed in px/s along the readout, the readout time measured in Diagnostics (target ±3 %, P0.8, design §6.16) and the frame's rows (no scale needed), shows it and records it per run, and warns when MD is more than 10° from the readout direction (shear instead of stretch); FR-CAL-04 corrects it (P9). | P0, P3, P9 | Planned |
| NFR-ACC-08 | Statistical precision is visible. | Run screen and `Summary.json` show the 95 % confidence intervals; a run of 100 non-overlapping shots typically reaches ±0.5° on the mean angle (informational). | P1, P5 | Planned |

### 6.3 Performance (NFR-PERF)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-PERF-01 | Capture keeps its frame rate while analysis runs; analysis has its own queue; no unbounded queues; camera buffers are released quickly (the ROI is copied out). | No drop in capture rate with analysis on (P8 V1). | P3, P8 | Planned |
| NFR-PERF-02 | Analysis time per shot on the iPhone 17 Pro Max for a 2,000 × 2,000 px ROI. | Proposed: ≤ 150 ms (Edge orientation), ≤ 300 ms (Flake edges), so ≥ 3 shots/s at that ROI (P8 V2). | P1, P2, P8 | Planned |
| NFR-PERF-03 | Responsive UI. | Live values ≤ 4 Hz, overlay ≤ 5 fps, no main-thread work longer than 16 ms per update. | P4 | Planned |
| NFR-PERF-04 | Remote link. | Status 4 Hz; preview 2–5 fps at about 640 px; command answer ≤ 1 s at 5 m line of sight (P8). | P6, P8 | Planned |
| NFR-PERF-05 | Sustained runs on USB-C power. | 60-minute run without thermal shutdown. At *serious* thermal state preview and overlay slow down and the analysis rate may be capped with a visible notice; at *critical* the run stops and saves (P8). | P3, P5, P8 | Planned |

### 6.4 Reliability and data integrity (NFR-REL)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-REL-01 | A crash, kill or interruption during a run leaves a recoverable run; captured data is never deleted on failure. | Kill test (P8); unit tests of repair. | P5, P8 | Planned |
| NFR-REL-02 | Metadata files are written atomically; a run appears in the library once its `Run.json` exists (written at Start) and is marked *Recording* until Stop completes it. The active run is read-only until then: rename, note, delete, share and copy to the other phone are disabled for it, and the recovery scan skips it. A run that stops with an error is repaired by a recovery scan in the same launch and listed as incomplete with its error (design §3.6). | Code inspection. | P5 | Planned |
| NFR-REL-03 | The remote link cannot harm a run: own queue, never blocks capture or analysis, no file sends while a run is active. | Code inspection; P8. | P6 | Planned |
| NFR-REL-04 | Reproducibility: every run records the app version and build, all parameters and the camera state actually applied: format (size, binning, pixel format), frame duration, exposure, ISO, lens position, white balance, stabilization, video HDR, low-light boost, distortion correction, intrinsics, MD, absolute tilt, flake width, scale, rolling-shutter factor s and the ROI margin. | `Run.json` content. | P5 | Planned |

### 6.5 Storage and memory (NFR-STO)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-STO-01 | Data stored locally under the app's `Documents`, visible in the Files app. | Code inspection. | P5 | Planned |
| NFR-STO-02 | Bounded memory: analysis buffers are reused; memory does not grow with run length; samples are streamed to disk. | Instruments / memory gauge in a 60-minute run (P8). | P1, P5, P8 | Planned |
| NFR-STO-03 | Data volume shown before Start (results per minute, frame images per minute). | Code inspection. | P5 | Planned |

### 6.6 Usability (NFR-USE)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-USE-01 | Usable with gloves and at arm's length: primary actions ≥ 44 × 44 pt, readouts on dark panels over the picture. | Owner check (P8). | P4, P8 | Planned |
| NFR-USE-02 | The remote alone is enough for normal operation: setup, ROI, runs, results. | Owner check (P8). | P6, P8 | Planned |
| NFR-USE-03 | Validity is always visible: quality light with reasons, "—" for values without enough samples. | Code inspection. | P4 | Planned |
| NFR-USE-04 | Units as §4.3; metric first with imperial alongside. | Code inspection. | P4 | Planned |
| NFR-USE-05 | Screens fit any text size; readouts keep fixed places and shrink instead of wrapping (Phone LiDAR NFR-USE-06 pattern). | Owner check. | P4, P8 | Planned |

### 6.7 Maintainability and testability (NFR-MNT, NFR-TST)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-MNT-01 | Warning-free build; one folder per module; pure logic separated from device code; doc comments on non-obvious maths; units in names or comments. | CI: 0 warnings. | P0 | Implemented |
| NFR-MNT-02 | Requirements, design, plan with change log, `CLAUDE.md` and the user guide stay current with every change. | Definition of done in the plan. | All | Planned |
| NFR-TST-01 | Pure logic (statistics, estimators, MD estimation, quality metrics, scheduler, formats, remote protocol and crypto) is unit-tested in a host-less XCTest bundle on the iOS Simulator; CI runs it for every pull request. | CI `unit-tests` green. | P0, P1, P2, P5, P6 | Planned |
| NFR-TST-02 | Image tests of the estimators, of two kinds. **Parity**: a few small synthetic images rendered by `tools/lab` (8-bit PNG, ≤ 2 MB in all, synthetic only), with the lab's results as JSON in the app's angle convention, are test-bundle resources; the Swift results must match the lab's reference implementation of the same algorithm: *Edge orientation* from P1, within 0.05° on the mean and the spread; *Flake edges* once the lab has a Python reference of design §6.5 (P2.1), with tolerances set then. **Accuracy**: the Swift `SyntheticMat` renders mats at test time (seeded), and the results are checked against its truth with the NFR-ACC-02 conditions, tolerances and image counts. The test target is compiled with optimization so that the image tests fit the CI time. | Tests in CI. | P1, P2 | Planned |
| NFR-TST-03 | On-device behaviour and accuracy are validated with documented procedures and recorded results. | P8 records. | P7, P8 | Planned |

### 6.8 Security and privacy (NFR-SEC)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-SEC-01 | Only the permissions used: camera, Local Network (`NSBonjourServices` = `_flakescan._tcp`), photo-library add for the share sheet. No microphone, location or photo-library read. | `Info.plist`. | P0 | Implemented |
| NFR-SEC-02 | Local only: no internet services, analytics or accounts; the only network use is the remote link to the one paired phone. | Network code only in `Remote/`. | P6 | Planned |
| NFR-SEC-03 | Repository hygiene: no secrets, Apple IDs, keys, certificates, profiles, personal data, plant pictures or run data in git. | `.gitignore`, review. | P0 | Implemented |
| NFR-SEC-04 | Remote link security as Phone LiDAR NFR-SEC-06, including its documented pairing limitation (design §10.10). | Code review; unit tests. | P6 | Planned |
| NFR-SEC-05 | Values from the other phone are untrusted: sizes, ROI bounds and every parameter range are checked; no crash on bad peer input. | Unit tests. | P6 | Planned |
| NFR-SEC-06 | CI least privilege: read-only token, pinned actions and tools, secrets only in the TestFlight steps. | Workflow review. | P0 | Implemented |

### 6.9 Build and distribution (NFR-BLD)

| ID | Requirement | Measure / target | Phase | Status |
|---|---|---|---|---|
| NFR-BLD-01 | Builds run on GitHub Actions (`macos-26`, Xcode 26.x); XcodeGen generates the project; no `.xcodeproj` in git; build number = workflow run number. | Workflow `Build iOS app`. | P0 | Implemented |
| NFR-BLD-02 | Unsigned `.ipa` artifact for Sideloadly; optional TestFlight job (four secrets, as Phone LiDAR). | Artifacts on each run. | P0 | Implemented |
| NFR-BLD-03 | CI diagnostics: errors, warning count and failed tests on the run summary; logs kept as artifacts. | Run summary. | P0 | Implemented |
| NFR-BLD-04 | Bundle ID `ca.gervais.flakescanner`, distinct from Phone LiDAR, so both apps install side by side. | `project.yml`. | P0 | Implemented |

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
| ASM-03 | Line speed 100–1,000 mm/s (owner, Q-02); camera height 0.5–3 m (it varies and is measured, FR-CAL-02); strands 75–150 × 10–25 mm (to be confirmed, Q-03). |
| ASM-04 | Light: the 1 px blur budget needs a shutter of at most mm/px ÷ speed: 1/2,800 s at 1,000 mm/s and 0.36 mm/px (about 1 m camera height), 1/5,600 s at 0.18 mm/px (about 0.5 m). With the main camera (f/1.78) at ISO 1,600 (the forecast's provisional limit until the probe measures the image noise, design §6.18) that takes about 1,300 lux on the mat at 1/2,800 s and 2,700 lux at 1/5,600 s, more than most plant halls have, so at many locations a flicker-free LED light will be needed. The light differs from location to location (Q-04), so the conditions forecast tells the user at each mount whether the light is enough for the speed and how much more is needed (FR-QUAL-08). Slower lines or a higher mount need proportionally less. |
| ASM-05 | "The Lidar app" in the owner's request is Phone LiDAR; its remote link (pairing code, direct Wi-Fi, auto-reconnect, copy) is the model, extended with a live preview so the ROI can be drawn on the remote (Q-07). |

## 8. Open questions

| ID | Question | Why it matters | Default until answered |
|---|---|---|---|
| Q-01 | Where will the camera look: the mat surface on the belt after which forming head, face or core layer? (Or strands falling from the orienter?) | Target direction, lighting, expected alignment, whether flakes are on a surface. | Partly answered 2026-11-23: the camera is directly over the line. Until the layer is known: mat surface on the belt; target 0° (face layer), selectable. |
| Q-02 | Line speed range and the possible camera height above the mat. | Shutter (blur), analysis rate, coverage, resolution. | Answered 2026-11-23: 100–1,000 mm/s; the camera height varies and is measured by the LiDAR (FR-CAL-02), assumed 0.5–3 m. |
| Q-03 | Typical strand length and width; how regular are the edges? | Default flake width, minimum edge length, ROI size. | 75–150 × 10–25 mm. |
| Q-04 | Lighting at the mount (LED, metal halide, fluorescent?) and roughly how bright? Can a flicker-free LED light be added? | The shutter that keeps motion blur within budget usually needs more light than the hall gives (ASM-04); flicker and one-sided light bias angles (design §6.13). | Answered 2026-11-23: the lighting varies by location. No fixed light is assumed: the conditions forecast rates each mount's light against the line speed and says how much more is needed (FR-QUAL-08); the light is checked at Start (design §6.16) and banded shots are corrected or left out (design §6.2). |
| Q-05 | Which statistics do you report today (mean angle, % within ±20° or ±30°, orientation index…), and is there a reference method to compare with (hand measurement on photos, a commercial system)? | Headline numbers, accuracy targets, validation. | §4.2 set; targets in §6.2. |
| Q-06 | Model and iOS version of the second iPhone. | Deployment target for the remote role. | iOS 17 or later. |
| Q-07 | Is "the Lidar app" your Phone LiDAR app? | Reuse of its remote link. | Yes (ASM-05). |
| Q-08 | GitHub repository for this app (name, public or private). | CI is the only compiler. | Answered 2026-11-23: `AliG1111/FlakeScanner`, public, created by the owner. |
| Q-09 | A 30–60 s video and a few photos of the mat from the intended mount position (kept out of the public repository); later the device probe's sample frames (P0.8). | Tuning and validating the methods on real flakes before P2. | No video yet (owner, 2026-11-23): synthetic images until the probe's frames (P0.8). |
| Q-10 | Install with Sideloadly (free, 7 days) or TestFlight (paid), as for Phone LiDAR? | Re-signing effort on the plant floor. | Same as Phone LiDAR. |

## 9. Traceability

Each requirement row above names its phases; each task line of the implementation plan names the requirement IDs it delivers, and `tools/docs/check_trace.py` checks that the two agree (every ID is cited by at least one task, and its phase column equals the phases of the tasks citing it). Status moves from *Planned* to *Implemented* at merge and to *Verified* when the on-device test that covers it is recorded.

| Group | Design sections | Plan phases | Tests |
|---|---|---|---|
| FR-APP | §3.1, §3.8, §6.16 | P0, P2, P3, P4, P6 | Diagnostics self-test; UI check (P8) |
| FR-CAP | §3.2, §5, §6.10–6.12 | P0, P2, P3, P4, P5 | Unit (format ranking); device probe (P0.8); device (P8 V1) |
| FR-ROI | §3.6, §6.1 | P1, P4, P6, P11 | Unit (mapping); device |
| FR-RATE | §6.9, §6.11 | P2, P3, P4, P5 | Unit (scheduler, coverage) |
| FR-DIR | §6.8 | P2, P3, P4, P5, P6, P8 | Unit (synthetic motion); device (P8 V4) |
| FR-MEAS | §6.2–6.5 | P1, P2, P4, P10 | Unit (fixtures, invariance); device (P8 V5, V7) |
| FR-STAT | §6.6, §6.7 | P1, P2, P3, P4, P5, P9 | Unit |
| FR-QUAL | §6.2, §6.10, §6.16, §6.18 | P0, P1, P2, P3, P4, P5 | Unit (synthetic blur, banding rules on the lab's E4 cases, flicker on E13's, conditions forecast); device probe (noise per ISO); device |
| FR-CAL | §6.5, §6.12, §6.15, §6.17 | P0, P2, P3, P4, P5, P8, P9 | Unit (width estimate, target detection, distance from depth maps); device probe (LiDAR distance); device (P8 V3, V5, V6) |
| FR-RUN, FR-LIB, FR-EXP | §7, §8, §9 | P4, P5, P11 | Unit (formats, repair); device (P8 V9, V11) |
| FR-RMT | §3.7, §6.14, §10.10 | P6 | Unit (protocol, crypto, loopback); device (P8 V8) |
| NFR | as cited in each row | as each row | as each row's measure |

## 10. Document history

| Date | Change |
|---|---|
| 2026-11-23 | First version: requirements for v1 (M1) and later phases, from the owner's request (flake angle statistics, remote control like Phone LiDAR, accuracy over speed with a user-set shot rate, ROI drawn by dragging a box) and Phone LiDAR's operating context. |
| 2026-11-23 | M0 review cycle 1 fixes ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md)): accuracy targets per condition with error bars (NFR-ACC-02); required flake width (FR-CAL-07); diagnostics and device probe (FR-APP-06); test-target mode designed (FR-CAL-06); display range around the target and signed deviations (§4.1); capture settings fixed and recorded (FR-CAP-02/03, NFR-REL-04); rolling-shutter and tilt targets restated (NFR-ACC-06/07); light needed for the blur budget (ASM-04); MD change and absolute level (FR-DIR-04, FR-QUAL-06); scheduler, snapshots, *Both*, library timing, settings versioning; phase column derived from the plan's task lines. |
| 2026-11-23 | M0 review cycle 2 fixes ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md), M0-22…M0-36): mains flicker found by a light check at 1/27 s plus a brightness-drift warning, since 1/30 s frames hide 60 Hz flicker (FR-QUAL-04, FR-APP-06); readout time fitted, s in pixels (NFR-ACC-07); moving test target referenced to the markers' track (FR-CAL-06, NFR-ACC-03/04); flake width stored with its camera and format, cross-check 0.75–2 × (FR-CAL-07); shots held through the MD-change confirmation (FR-DIR-04); skipped shots exclude stops (FR-RATE-02); the run being recorded is read-only (NFR-REL-02, FR-RUN-05/07, FR-LIB-04, FR-RMT-10); image counts fixed in advance (NFR-ACC-02). |
| 2026-11-23 | M0 review cycle 3 fixes ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md), M0-37…M0-48): banding measured by band gradient and darkest row, with near-dark shots excluded and strong bands corrected (*Edge orientation*) or excluded (*Flake edges* across the readout) after deep PWM bands in lab E4 (FR-QUAL-04 a, FR-MEAS-04); brightness drift per strip with the exposure locked and the light check at Start (FR-QUAL-04 b, c); readout time from the phase slope of the flicker, lab E13 (NFR-ACC-07, FR-APP-06); a busy analysis no longer shifts the shot schedule, rates per moving time (FR-RATE-02); the MD-change hold sized from the MD window and the configured confirmation (FR-DIR-04); sharing only finished runs, recovery skips the current launch (FR-LIB-03, NFR-REL-02, FR-RUN-05). |
| 2026-11-23 | Owner's answers (Q-01 in part, Q-02, Q-04, Q-09) and a new requirement: the scanner phone has LiDAR; lighting varies by location; feedback when the results will be poor for the speed and the light (FR-QUAL-08, design §6.18, lab E14 planned for its noise thresholds); camera directly over the line; line speed 100–1,000 mm/s (ASM-03; shutter and light numbers in ASM-04 and FR-QUAL-03; rolling-shutter numbers in NFR-ACC-07); the camera height varies from mount to mount and is measured with the LiDAR at Start and in Setup (FR-CAL-02, design §6.17; FR-CAL-03 keeps only the perspective correction); a stored flake width is rescaled to a new camera distance (FR-CAL-07); no video yet, so synthetic images until the probe's frames. |
| 2026-11-24 | M0 review cycle 4 fixes ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md), M0-49…M0-60): the banding rule keyed on the strands' direction to the sensor rows instead of MD against the readout, with a band metric that does not grow as the ROI narrows; *Flake edges* left out of banded shots and *Edge orientation* corrected in the run's regime, after lab E4 over strand directions, alignments and widths (FR-QUAL-04 a, FR-MEAS-04); the readout test as two bursts, the second turned 180°, with plausibility checks (FR-APP-06 c); the forecast's light limits as contrast-to-noise ratios from lab E14 and a *Light bands* factor (FR-QUAL-08, ASM-04); a run that stops with an error recovered in the same launch (NFR-REL-02, FR-RUN-05); the achieved-rate bound restated (FR-RATE-02). |
| 2026-11-24 | M0 review cycle 5 fixes ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md), M0-61…M0-78): the banding regime of *Edge orientation* decided once per run from the strands' direction to the rows and the flake width, and *Flake edges* excluded from weak bands, after lab E4 over weak bands, the regime boundary and wide strands, with the residuals stated (FR-QUAL-04 a); the forecast's share of shots with light bands, its contrast and light limits restated from a refined E14, the highest expected speed a setting (FR-QUAL-08); the flake width stored with the latest LiDAR reading (FR-CAL-07). |
