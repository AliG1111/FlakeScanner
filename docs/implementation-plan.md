# Flake Scanner — Implementation plan

| | |
|---|---|
| Document | Process, model delegation, self-review, review protocol, phased checklists, change log |
| State | Planning (P0.1) in the M0 review cycle ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md)): cycle 1 found 21 issues, fixed in the docs; the re-review is next. App skeleton and CI (P0.3, P0.4) written on the branch `p0-skeleton`; their first compile waits for the GitHub repository (P0.2). Then: P0.5–P0.8 (CI green, device probe), owner's look at the plan. |
| Date | 2026-11-23 |
| Related | [requirements.md](requirements.md), [design.md](design.md), [../CLAUDE.md](../CLAUDE.md), [reviews/](reviews/) |

Agents keep this file current: tick a task when its PR is merged, add a change-log row for every merged PR or docs revision, and add newly found work to P11.

---

## 1. Overview

| Phase | Content | Milestone | State |
|---|---|---|---|
| P0 | Bootstrap: planning docs and lab (milestone M0), GitHub repository, XcodeGen app skeleton, CI (build, unit tests, optional TestFlight), device probe build and its run at the line | M0, M1 | P0.1 in review; P0.3–P0.4 written, not yet compiled |
| P1 | Measurement core I: axial statistics, image buffers and filters, *Edge orientation*, quality metrics, synthetic mats in Swift | M1 | Not started |
| P2 | Measurement core II: *Flake edges* with collinear merging, flake width, motion and machine direction, frame analyzer, scheduler and coverage, test-target detection | M1 | Not started |
| P3 | Capture pipeline on the device: camera, formats, exposure/focus locks, shots, level, scale | M1 | Not started |
| P4 | Scan screen: ROI editor, live statistics, quality light, settings, start/stop, snapshot | M1 | Not started |
| P5 | Runs: recording files, recovery, library, charts, sharing; test-target mode | M1 | Not started |
| P6 | Remote link: Phone LiDAR port, live preview, ROI and settings from the remote, run copy | M1 | Not started |
| P7 | Milestone M1 final review, user guide, on-device validation procedures | M1 | Not started |
| P8 | On-device validation on the iPhone 17 Pro Max (owner, with agent analysis) | M2 | Not started |
| P9 | Accuracy enhancements: LiDAR scale and tilt, rolling-shutter and lens corrections, flake size, still/RAW mode evaluation | M2 | Not started |
| P10 | Optional ML per-flake method (owner decision after P8) | M3 | Not started |
| P11 | Backlog | — | Open |

Milestone M0 is the planning baseline: requirements, design, this plan, `CLAUDE.md` and the lab (P0.1), reviewed until a review finds nothing new. Milestone M1 is the first installable app with everything in requirements §1 "in scope for v1". Build numbers will be GitHub Actions run numbers of the `Build iOS app` workflow on `main`.

## 2. Model and reasoning matrix

| Task type | Model | Reasoning |
|---|---|---|
| Requirements, architecture, design, planning, major design changes; analysis of on-device validation results that changes the design | Opus 5.5 | max |
| Milestone final review: whole codebase, tests and user guide, once per milestone | Opus 5.5 | max |
| Change review of a PR (the diff plus the code it calls or is called by: correctness, defects, security, performance, concurrency, measurement maths); re-reviews of fixes | Opus 5.5 | high |
| Measurement code: estimators, statistics and confidence intervals, motion and MD, quality metrics, scheduler, frame analyzer (`Analysis/`, `Motion/`, `Statistics/`, pure parts of `Capture/`); lab experiments, fixtures and reference results (`tools/lab`) | Opus 5.5 | high |
| Capture pipeline, concurrency, file formats and recovery (`Capture/CapturePipeline`, `Runs/`); remote link networking, crypto and protocol (`Remote/` except views) | Opus 5.5 | high |
| SwiftUI views, settings screens, charts, sharing, wiring | Sonnet 5.5 | high |
| Unit tests (the agent that writes measurement code designs its test cases; Sonnet writes the rest) | Sonnet 5.5 | high |
| CI log triage and compile-error fixes | Sonnet 5.5 | medium |
| Docs upkeep (user guide, change log, checklists, `CLAUDE.md`); wording follow-ups after a final review | Sonnet 5.5 | medium |
| Bookkeeping checks (review record, change log, ticks against git and CI) and few-line edits | Orchestrator, no agent | — |
| Mechanical work (renames in the port, formatting, inventories, searches) | Haiku 5.5 | low |

- The agent that did a task self-reviews it at the same model and level before committing (§4).
- Change reviews and milestone final reviews are done by a fresh agent that did not write the code.
- A task touching both measurement or capture code and UI takes the higher assignment.
- Small edits the orchestrator can make in a few lines are made directly; starting an agent costs more than the edit.
- Every checklist line in §6 names its requirement IDs in brackets and ends with its assignment `(Model / level)`; on-device tests name the owner and the analysing agent.

## 3. Per-task workflow

1. **Pick** an unchecked task; the orchestrator delegates it at the model and level on its line.
2. **Branch** from the latest `main`: `git fetch origin && git switch -c <short-kebab-topic> origin/main`. One topic per branch.
3. **Implement** in small commits at each verified unit of work: imperative subject (≤ 72 characters), a body that says why, and the trailer from `CLAUDE.md`.
4. **Self-review** against §4 at the same model and level; fix what it finds before pushing.
5. **CI**: push the branch and run `Build iOS app` (dispatch or PR). App build and unit tests green with 0 warnings. Fix and repeat; after a failure re-run only what failed while fixing.
6. **PR** into `main`: summary, requirement IDs (FR-/NFR-), design sections, review finding IDs fixed, test evidence (CI run number), self-review notes. Agents never push to `main`; the owner merges, or the orchestrator when the owner asks.
7. **After merge**: tick the task, add the change-log row (date, build number of the merge build, PR, summary), update requirement statuses and the design if behaviour or formats changed, note user-visible changes in the user guide (`README.md`), update `CLAUDE.md` when a convention or command changed.

**Token budget** (the owner's rules for Phone LiDAR, adopted here; the owner can change them):
- One session per task or phase, starting from `CLAUDE.md` and this plan.
- At most two agents at a time; one agent does an area's fix and its tests together.
- Read only what the task needs: the diff, the touched files and their direct callers; grep before opening large files.
- CI: dispatch once, then one `gh run watch <id> --exit-status`; on failure read only `--log-failed`.
- Finding counts live only in the review record; the change-log row is written once, at merge.

## 4. Self-review checklist

Run before every commit that completes a unit of work. Record anything left open in the PR body.

- [ ] **Measurement correctness** — matches the requirement IDs and design sections; axial wrap to (−90°, 90°] and doubled-angle maths used everywhere angles are averaged; angle sign and MD conversion through `AngleFrame` ([design §6.1](design.md#61-coordinates-and-the-angle-convention)); units in names (deg, px, mm, s); one formula checked by hand on an example.
- [ ] **Bias awareness** — no new filter, threshold, resampling or weighting that depends on direction without a test showing it adds no orientation bias (rotation test at every degree for estimators).
- [ ] **Determinism** — same input and parameters give identical results (no unordered reductions over dictionaries or sets, no time or random seeds in measurement code).
- [ ] **Defects and edge cases** — empty ROI, ROI at the frame edge, frame size change, no texture, no movement, MD not detected, 0 or 1 sample, all angles equal, R → 0, NaN/∞ (`JSONEncoder` throws on non-finite numbers), integer overflow (width × height), index bounds.
- [ ] **Concurrency** — each piece of state has one owner (main actor, capture data queue, analysis queue, run I/O queue, remote queue); values cross queues; camera buffers are not held across queues; no blocking work on the main actor; cancellation checked after `await`; observers and timers torn down.
- [ ] **Memory and resources** — no growth with run length; analysis buffers pooled; pixel-buffer locks balanced; file handles closed.
- [ ] **Data integrity** — metadata written atomically; captured data never deleted on failure; formats backward compatible (optional new fields, `formatVersion`).
- [ ] **Error handling** — failures reach the user with a clear message; no `try?` on paths that read or write measurement data unless the fallback is documented.
- [ ] **Security and privacy** — no secrets, Apple IDs, keys, personal data, plant pictures or run data committed; network code only in `Remote/`, authenticated and encrypted, peer values validated (sizes, ROI bounds, parameter ranges); new permissions have purpose strings; workflow keeps least privilege.
- [ ] **Build hygiene** — 0 warnings in CI; no force unwraps on file, device or peer data; no debug `print`.
- [ ] **Tests** — unit tests added or updated for changed pure logic; lab reference results and test tolerances changed only with a reason in the PR.
- [ ] **UI** — portrait, readable on dark panels over the picture, touch targets ≥ 44 pt, accessibility labels on icon buttons, fixed readout cells.
- [ ] **Docs** — requirements status, design, this plan (tick, change log), user guide and `CLAUDE.md` updated as needed.

## 5. Review protocol

Severity:
- **Critical** — crash, data loss or corruption, security or privacy exposure, wrong measurement written to output files or shown as valid.
- **High** — wrong results in common use, likely thread-safety bug, leak during capture, CI or build break.
- **Medium** — wrong behaviour in edge cases, missing user-visible error handling, performance problem that affects use.
- **Low** — maintainability, naming, duplication, minor UX polish.

Cycle: review → triage → fix → CI green → re-review of the fixes and the code they touch → repeat **until a review yields no new findings** (owner's rule). "New" means any finding of any severity not already fixed or recorded in P11 with a reason. Critical, High and Medium are always fixed; a Low is fixed or, when the fix is risky or large, deferred to P11 with a reason.

- **Change review**: every PR that changes code or tests gets one fresh Opus 5.5 / high reviewer on the diff plus its callers and callees. Re-reviews read the fix diff.
- **First review of a large new subsystem** (the measurement core in P1–P2, the ported remote link in P6): area-split reviewers, then the normal cycle.
- **Milestone final review**: one fresh Opus 5.5 / max review of the whole codebase, tests and user guide at the end of each milestone (P7 for M1); code findings are fixed and re-reviewed at Opus 5.5 / high; wording findings are fixed without another review.
- **Docs**: requirements, design, plan and `CLAUDE.md` are reviewed when their content changes; bookkeeping (review record, change log, ticks) is checked by the orchestrator against git and CI.
- Every branch has a green CI run at its head before merge.
- Each cycle is recorded in `docs/reviews/<YYYY-MM-DD>-<milestone or phase>.md`: finding ID, severity, file:line, summary, fix, status.

## 6. Phased checklists

Each task line names the requirement IDs it delivers in brackets and ends with its assignment. The requirements' phase column is derived from these lines; `python3 -I tools/docs/check_trace.py` checks both files agree (`--fix` rewrites the phase column from this plan).

### P0 — Bootstrap and device probe

Design §3.8, §6.16, §10.8, §10.11.

- [ ] P0.1 Requirements, design, implementation plan, `CLAUDE.md`, algorithm lab with first results; docs review until no new findings, recorded in `docs/reviews/2026-11-23-M0.md` [NFR-MNT-02] (Opus 5.5 / max)
- [ ] P0.2 GitHub repository created by the owner (Q-08); push `main` with the planning commits (orchestrator)
- [ ] P0.3 `project.yml` (app + host-less test target, warnings as errors, bundle ID `ca.gervais.flakescanner`), `Support/Info.plist` (camera, Local Network `_flakescan._tcp`, photo add, file sharing, portrait), app icon, app skeleton (Home with disabled entries, About with version and build), first pure files with unit tests [FR-APP-01, NFR-PLAT-01, NFR-PLAT-02, NFR-MNT-01, NFR-SEC-01, NFR-SEC-03, NFR-BLD-04, NFR-TST-01] (Sonnet 5.5 / high)
- [ ] P0.4 CI workflow ported from Phone LiDAR (`unsigned-ipa`, `unit-tests`, optional `testflight`; names changed; actions and XcodeGen pinned; hash-locked `codemagic-cli-tools`) [NFR-BLD-01, NFR-BLD-02, NFR-BLD-03, NFR-SEC-06] (Sonnet 5.5 / medium)
- [ ] P0.5 CI green with 0 warnings; README steps 1–3 (repository, cloud build, Sideloadly / TestFlight install) [NFR-MNT-01] (Sonnet 5.5 / medium)
- [ ] P0.6 Change review until no new findings (Opus 5.5 / high)
- [ ] P0.7 Device probe build: Settings › Diagnostics with the camera report, sample bursts with per-frame camera data, flicker index and readout test, zip export (design §3.8, §6.16); pure parts unit-tested; change review [FR-APP-06, NFR-TST-01] (Opus 5.5 / high; screens Sonnet 5.5 / high)
- [ ] P0.8 Probe on the iPhone 17 Pro Max at the line (owner, with a written procedure): format list, binning, distortion correction with intrinsics, capture rate per format, readout direction and time, plant light level, flicker and the exposure the light allows, sample frames of real flakes (Q-09); agent analysis recorded in `docs/validation/`, design and requirements updated before P1 [FR-CAP-02, FR-CAP-03, NFR-ACC-07] (owner; analysis Opus 5.5 / high, Opus 5.5 / max when the design changes)

### P1 — Measurement core I

Design §6.2–6.4, §6.6, §6.7, §6.10.

- [ ] P1.1 `AxialAccumulator`, `AxialSummary`, deviation histogram, frame-cluster confidence intervals with the t quantile [FR-STAT-01, FR-STAT-02, FR-STAT-04, FR-STAT-05, FR-STAT-07, NFR-ACC-08] (Opus 5.5 / high)
- [ ] P1.2 `LumaImage`, `NormalizedRect` ↔ pixels with margins, `Kernels` (vImage separable Gaussian and derivative), `RowNormalizer` (per-row gain for *Edge orientation*, design §6.2) [FR-ROI-02, FR-MEAS-05, NFR-STO-02] (Opus 5.5 / high)
- [ ] P1.3 `TensorOrientation` (*Edge orientation*) [FR-MEAS-02, FR-MEAS-04, NFR-PERF-02] (Opus 5.5 / high)
- [ ] P1.4 `QualityMetrics`: clipping, sharpness, banding score, flicker index, texture [FR-QUAL-01, FR-QUAL-02, FR-QUAL-03, FR-QUAL-04, FR-QUAL-05] (Opus 5.5 / high)
- [ ] P1.5 Image-test basis (two kinds, NFR-TST-02): the lab's *Edge orientation* reference aligned exactly with design §6.3–6.4 (kernels, radius, borders, grid, weights); a fixture exporter for a few small synthetic PNGs (≤ 2 MB in all) with truth and lab results as JSON in the app's angle convention (sign flipped from the lab's image angles), bundled as test resources (parity); `SyntheticMat` in Swift for the accuracy tests; the test target compiled with optimization [NFR-TST-02] (Opus 5.5 / high)
- [ ] P1.6 Unit tests: statistics against hand-computed values; rotation invariance at every degree; *Edge orientation* parity with the lab fixtures (0.05°); accuracy on `SyntheticMat` mats in the NFR-ACC-02 conditions with enough images that each SE is at most a third of its tolerance (this settles the lab's open mean-error cases, such as *Edge orientation* at 45°); banding correction; quality metrics; determinism [NFR-ACC-01, NFR-ACC-02, NFR-TST-01, NFR-TST-02] (Sonnet 5.5 / high; test cases designed by the P1.1–P1.5 agent)
- [ ] P1.7 CI green; area-split first review of the measurement core, fixes, re-reviews until no new findings (Opus 5.5 / high)

### P2 — Measurement core II

Design §6.1, §6.5, §6.8–6.11, §6.15.

- [ ] P2.1 Lab: Python reference of the §6.5 detector (replacing OpenCV's LSD in the comparisons); tune merging and edge parameters on the probe's real frames and on synthetic sweeps, aiming at the NFR-ACC-02 targets for weaker alignment; improve the flake-width estimate and check the 12 px minimum; export *Flake edges* fixtures and reference results [NFR-ACC-02, NFR-TST-02] (Opus 5.5 / high)
- [ ] P2.2 `EdgeSegmentDetector` (LSD-style line-support regions, sub-pixel axis, NFA, clipping at the ROI border) [FR-MEAS-01, FR-MEAS-05, NFR-PERF-02] (Opus 5.5 / high)
- [ ] P2.3 `CollinearMerger`, `FlakeWidth` [FR-MEAS-01, FR-CAL-07] (Opus 5.5 / high)
- [ ] P2.4 `PhaseCorrelator`, `MotionEstimator`, `DirectionTracker` (MD, speed, line stopped, MD change) [FR-DIR-01, FR-DIR-04, FR-DIR-05, FR-RATE-04, NFR-ACC-03] (Opus 5.5 / high)
- [ ] P2.5 `AngleFrame`, `FrameAnalyzer` (both methods, overlay primitives, timing) [FR-MEAS-03, FR-MEAS-04, FR-STAT-01] (Opus 5.5 / high)
- [ ] P2.6 `ShotScheduler`, `Coverage`, `ExposurePlanner`, `CameraFormats` (pure) [FR-RATE-02, FR-RATE-03, FR-CAP-02, FR-QUAL-03, NFR-ACC-05] (Opus 5.5 / high)
- [ ] P2.7 Test target: `tools/lab/make_target.py` (PDF and layout JSON), `TargetLayout`, `TargetDetector`, `TargetMatcher` (pure, tested on rendered target images) [FR-CAL-06] (Opus 5.5 / high)
- [ ] P2.8 Self-test of Diagnostics on bundled fixtures [FR-APP-06] (Opus 5.5 / high)
- [ ] P2.9 Unit tests: single-edge bias at every degree; *Flake edges* parity with the lab fixtures and accuracy on `SyntheticMat` mats (NFR-ACC-02 conditions and image counts); merging and ROI-border cases; width estimate; synthetic translations in all directions with sub-pixel shifts and MD standard error; angle sign; scheduler timing (no bursts, skip counts); coverage; format ranking; target detection and matching [NFR-ACC-01, NFR-ACC-02, NFR-ACC-03, NFR-TST-01, NFR-TST-02] (Sonnet 5.5 / high; test cases designed by the P2.1–P2.8 agents)
- [ ] P2.10 CI green; area-split first review (estimators and merging; motion, scheduler and formats; test target), fixes, re-reviews until no new findings (Opus 5.5 / high)

### P3 — Capture pipeline

Design §3.2, §4, §5, §6.10.

- [ ] P3.1 `CapturePipeline`: physical camera and ranked format, fixed image processing (stabilization, video HDR, low-light boost off; fixed frame duration), distortion correction and intrinsics, exposure / focus / white balance / torch with locks, video output on the data queue, motion per frame, scheduler, ROI copy into the buffer pool, analysis hand-off, interruption / error / system-pressure / thermal handling [FR-CAP-01, FR-CAP-02, FR-CAP-03, FR-CAP-04, FR-CAP-05, FR-CAP-06, FR-CAP-07, FR-CAP-09, FR-CAP-10, FR-RATE-01, FR-RATE-02, FR-RATE-04, FR-DIR-01, FR-DIR-04, FR-DIR-05, FR-QUAL-01, FR-QUAL-02, FR-QUAL-03, FR-QUAL-04, FR-STAT-01, NFR-ACC-05, NFR-PERF-01, NFR-PERF-05] (Opus 5.5 / high)
- [ ] P3.2 `LevelMonitor` (absolute tilt, zero for bump detection); scale from the entered distance and the intrinsics; rolling-shutter factor s [FR-QUAL-06, FR-CAL-01, FR-CAL-02, NFR-ACC-06, NFR-ACC-07] (Opus 5.5 / high)
- [ ] P3.3 Camera permission flow (port) [FR-APP-04] (Sonnet 5.5 / high)
- [ ] P3.4 CI green; change review until no new findings (Opus 5.5 / high)

### P4 — Scan screen

Design §3.6.

- [ ] P4.1 `ScanModel`: states, start/stop rules (MD gate, flake width set, storage), coalesced live snapshots, settings apply and validation [FR-RUN-01, FR-DIR-03, FR-APP-05, FR-STAT-07, FR-ROI-04, NFR-PERF-03] (Opus 5.5 / high)
- [ ] P4.2 `ScanView` layout (Phone LiDAR pattern), `CameraPreview`, `OverlayView` (ROI, MD arrow and "+" arc, edges coloured by angle), screen kept awake [FR-APP-02, FR-APP-03, FR-CAP-08, NFR-USE-01, NFR-USE-03, NFR-USE-05] (Sonnet 5.5 / high)
- [ ] P4.3 `ROIEditor` (draw, move, resize, minimum size) with unit-tested screen ↔ frame mapping; manual MD line; flake-width measuring tool [FR-ROI-01, FR-ROI-02, FR-ROI-03, FR-ROI-05, FR-DIR-02, FR-CAL-07] (Sonnet 5.5 / high; mapping maths Opus 5.5 / high)
- [ ] P4.4 `LiveStatsPanel`, `QualityPanel`, mini histogram, coverage, tilt-bias and rolling-shutter readouts, settings sheet with *Advanced* [FR-STAT-02, FR-STAT-03, FR-STAT-04, FR-STAT-06, FR-QUAL-07, FR-RATE-01, FR-RATE-03, FR-MEAS-03, FR-MEAS-04, NFR-ACC-06, NFR-USE-04] (Sonnet 5.5 / high)
- [ ] P4.5 Snapshot; Home entries enabled as their screens land [FR-RATE-05, FR-APP-01] (Sonnet 5.5 / high)
- [ ] P4.6 CI green; change review until no new findings (Opus 5.5 / high)

### P5 — Runs, library, export and test-target mode

Design §6.15, §7–§9.

- [ ] P5.1 `RunFormats` (`Run.json`, CSV encoders), `RunStore` [FR-RUN-02, FR-EXP-01, FR-EXP-02, NFR-REL-02, NFR-REL-04, NFR-STO-01] (Opus 5.5 / high)
- [ ] P5.2 `RunRecorder`: streamed CSVs, frame images (PNG with margin, HEIC, overlay), snapshots, marker, storage checks, auto-stop, MD-change stop, summaries at Stop [FR-RUN-03, FR-RUN-04, FR-RUN-06, FR-RATE-05, FR-DIR-04, FR-CAP-10, NFR-STO-02, NFR-STO-03, NFR-PERF-05] (Opus 5.5 / high)
- [ ] P5.3 `RunRecovery`: repair of cut-off files, incomplete runs in the library [FR-RUN-05, NFR-REL-01] (Opus 5.5 / high)
- [ ] P5.4 Library: runs list, run screen, histogram / rose / time-series charts, frame browser, share, rename and note, delete one or several [FR-LIB-01, FR-LIB-02, FR-LIB-03, FR-LIB-04, FR-RUN-07, FR-STAT-02, FR-STAT-03, FR-QUAL-07, NFR-ACC-08] (Sonnet 5.5 / high)
- [ ] P5.5 Test-target mode on the scan screen, target report and its files [FR-CAL-06] (Opus 5.5 / high; screens Sonnet 5.5 / high)
- [ ] P5.6 Unit tests: formats, repair, store, summaries, confidence intervals end to end [NFR-TST-01] (Sonnet 5.5 / high)
- [ ] P5.7 CI green; change review until no new findings (Opus 5.5 / high)

### P6 — Remote link

Design §3.7, §6.14, §10.10, §10.11.

- [ ] P6.1 Port the Phone LiDAR files listed in design §3.7 with their tests and the small adapters they need (`SpeedText`, a run record in place of `ScanRecord`, store calls; renames: service `_flakescan._tcp`, transcript label, queue names); CI green before any behaviour change [FR-RMT-01, FR-RMT-02, FR-RMT-03, FR-RMT-04, FR-RMT-05, FR-RMT-10, NFR-SEC-04, NFR-TST-01] (Opus 5.5 / high; renames Haiku 5.5 / low)
- [ ] P6.2 Protocol extensions: scanner status, settings patches with the schema version, ROI / MD / refocus / snapshot commands, preview record and subscription; validation of peer values (pure, with tests) [FR-RMT-06, FR-RMT-07, FR-RMT-09, FR-RMT-12, NFR-SEC-05] (Opus 5.5 / high)
- [ ] P6.3 Scanner side: `RemoteScannerTarget` on `ScanModel`, preview downscale and JPEG with one frame in flight, scan screen kept open after a run [FR-RMT-11, FR-APP-03, FR-DIR-03, NFR-REL-03, NFR-PERF-04] (Opus 5.5 / high)
- [ ] P6.4 Remote side: link logic for preview and settings; `RemoteControlView` with preview, `ROIEditor`, controls, statistics and runs copy; Home *Connect to the other phone* [FR-RMT-08, FR-ROI-01, NFR-USE-02, NFR-SEC-02] (link logic Opus 5.5 / high; screens Sonnet 5.5 / high)
- [ ] P6.5 CI green (Sonnet 5.5 / medium)
- [ ] P6.6 Area-split first review (ported networking and crypto; extensions and UI), fixes, re-reviews until no new findings (Opus 5.5 / high)

### P7 — Milestone M1 review, user guide and validation procedures

- [ ] P7.1 Validation procedures `docs/validation/procedures.md`: setup, steps, data to share, analysis and pass criteria for every test of P8, and the V7 hand-measurement tool (`tools/handmeasure/`: the owner marks both ends of each counted flake on saved frames; rules for which flakes count: fully visible, length ≥ 3 × width, not cut by the ROI) [NFR-TST-03] (Opus 5.5 / high; tool Sonnet 5.5 / high)
- [ ] P7.2 User guide (`README.md`): install, mounting and lighting guidance, level, flake width, ROI, rate and coverage, methods and what they measure, quality light, runs and files, remote link, test target, diagnostics [NFR-MNT-02] (Sonnet 5.5 / medium)
- [ ] P7.3 Milestone M1 final review of the whole codebase, tests and guide (Opus 5.5 / max); code findings fixed and re-reviewed at Opus 5.5 / high until a review yields no new findings; record `docs/reviews/<date>-M1.md`
- [ ] P7.4 Requirement statuses, `CLAUDE.md`, change log [NFR-MNT-02] (Sonnet 5.5 / medium; orchestrator checks bookkeeping)

### P8 — On-device validation (iPhone 17 Pro Max)

The owner runs each test with its procedure from P7.1 and shares the run files; an agent analyses them (Opus 5.5 / high; Opus 5.5 / max when the result changes the design). Results are recorded in `docs/validation/`. The readout and plant-light tests run earlier, in the device probe (P0.8).

- [ ] V1 Capture timing with analysis on: capture rate stays at the format rate; achieved against requested rate [NFR-PERF-01] (owner; analysis Opus 5.5 / high)
- [ ] V2 Analysis time against ROI size and method; profiling; optimization if below the target [NFR-PERF-02] (owner; analysis Opus 5.5 / high)
- [ ] V4 MD against the printed target's bar on the moving belt, and the MD-change exclusion and stop [NFR-ACC-03, FR-DIR-04] (owner; analysis Opus 5.5 / high)
- [ ] V5 Printed target, still: angle sign, per-angle bias, spread [NFR-ACC-04, FR-CAL-06] (owner; analysis Opus 5.5 / high)
- [ ] V6 Printed target moving on the belt [NFR-ACC-04] (owner; analysis Opus 5.5 / high)
- [ ] V7 Real mat against hand-measured flakes (≥ 200 flakes on ≥ 5 saved frames, P7.1 tool) for both methods; choose defaults; record residual biases (R-01, R-02) [NFR-TST-03] (owner; analysis Opus 5.5 / max)
- [ ] V8 Remote link at the line: pairing, preview, ROI, controls, range and latency [NFR-PERF-04, NFR-USE-02] (owner; analysis Opus 5.5 / high)
- [ ] V9 60-minute run: heat, memory, storage [NFR-PERF-05, NFR-STO-02] (owner; analysis Opus 5.5 / high)
- [ ] V11 Kill and interruption during a run, recovery [NFR-REL-01] (owner; analysis Opus 5.5 / high)
- [ ] V12 Gloves, text sizes, readability on the mount and the remote [NFR-USE-01, NFR-USE-05] (owner; analysis Sonnet 5.5 / medium)

### P9 — Accuracy enhancements (milestone M2)

Scope set after P8 by the owner and an Opus 5.5 / max design update.

- [ ] P9.1 LiDAR distance and surface tilt → measured scale and perspective rectification [FR-CAL-03] (Opus 5.5 / high)
- [ ] P9.2 Rolling-shutter correction from the measured readout time and speed [FR-CAL-04, NFR-ACC-07] (Opus 5.5 / high)
- [ ] P9.3 Lens-distortion correction [FR-CAL-05] (Opus 5.5 / high)
- [ ] P9.4 Flake length and width statistics with the scale (Opus 5.5 / high)
- [ ] P9.5 Still / RAW capture mode evaluation against the target (R-14) (Opus 5.5 / high)
- [ ] P9.6 Milestone M2 final review (Opus 5.5 / max) and re-reviews (Opus 5.5 / high)

### P10 — ML per-flake method (optional, milestone M3)

- [ ] P10.1 Labelling workflow and dataset from saved frames (kept out of the public repository) [FR-MEAS-06] (Opus 5.5 / high)
- [ ] P10.2 Model training off the phone (Core ML instance segmentation), evaluation against hand measurements [FR-MEAS-06] (Opus 5.5 / high)
- [ ] P10.3 *Flakes (ML)* method in the app, validation, milestone M3 review [FR-MEAS-06] (Opus 5.5 / high; review Opus 5.5 / max)

### P11 — Backlog

- Exclusion masks [FR-ROI-06]; re-analysis of saved frames [FR-LIB-05]; summary report image or PDF; alarms and trend limits; Windows re-analysis script; operator-side / drive-side labels for the angle sign.
- Shared Swift package for the remote link with Phone LiDAR (R-12); Swift 6 language mode for both apps.
- Outputs to plant systems (PLC, historian, OPC UA) — owner decision.

## 7. Change log

Newest first. Build = run number of the `Build iOS app` workflow on `main` after the merge.

| Date | Build | PR / commit | Summary |
|---|---|---|---|
| 2026-11-23 | — (docs only, no repository on GitHub yet) | local `main`, M0 review fixes | M0 review cycle 1 ([reviews/2026-11-23-M0.md](reviews/2026-11-23-M0.md), 21 findings) fixed in the docs: device probe build and plant visit before the measurement core (P0.7, P0.8; Diagnostics, FR-APP-06); test-target mode (FR-CAL-06, design §6.15); required flake-width setting (FR-CAL-07); per-condition accuracy targets with standard errors (NFR-ACC-02); flicker split into short-period banding (corrected for *Edge orientation* only) and mains flicker (flicker index); rolling-shutter and tilt bounds corrected; remote settings patches with a schema version; histograms of the deviation from the target; parity and accuracy image tests (NFR-TST-02); every plan task names its requirement IDs, checked by `tools/docs/check_trace.py`. Lab rerun with 8 images per condition, error bars, controls for banding, and new experiments E10–E12 (flake width set wrong, width estimate, ROI border). |
| 2026-11-23 | — (docs only, no repository on GitHub yet) | local `main`, planning commit | P0.1: requirements (FR/NFR with phases, open questions Q-01…Q-10), design (architecture, algorithms, error budget, formats, technology choices, risks), this plan, `CLAUDE.md`, user-guide stub, and the algorithm lab `tools/lab/flake_lab.py` with results E1–E9 (mean angle accurate with both methods; *Flake edges* with collinear merging chosen as default; motion blur, flicker banding and one-sided light each cost 1–2° when uncontrolled). |
