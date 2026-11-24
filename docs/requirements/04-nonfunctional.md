# Requirements: non-functional (§6)

Part of the requirements ([summary](../requirements.md)). Section numbers are stable; cite them as §N.

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

