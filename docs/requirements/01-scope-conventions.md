# Requirements: purpose, context, use cases, conventions (§1–4)

Part of the requirements ([summary](../requirements.md)). Section numbers are stable; cite them as §N.

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
- Phase = the implementation-plan phase that delivers the requirement (P0–P11, [implementation-plan.md §6](../implementation-plan.md#6-phased-checklists)).
- Status values: **Planned**; **Implemented** (on `main`, CI green, behaviour confirmed by code inspection and simulator tests); **Implemented – not verified on device** (needs the iPhone or its camera); **Verified** (on-device validation recorded in P8); **Withdrawn**.

