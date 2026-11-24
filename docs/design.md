# Flake Scanner — Design (summary and index)

| | |
|---|---|
| Document | One-page summary and index of the design. The full text is split into per-topic files in [design/](design/). |
| Describes | The planned v1 (milestone M1) and the later phases. Source paths are relative to `FlakeScanner/` unless they start with `Support/`, `Tests/`, `tools/`, `.github/` or `project.yml`. |
| Date | 2026-11-23 (split into per-topic files 2026-11-24, P0.9; text unchanged) |
| Related | [requirements.md](requirements.md), [implementation-plan.md](implementation-plan.md), [../CLAUDE.md](../CLAUDE.md), lab [../tools/lab/](../tools/lab/) |

"Phone LiDAR" is the owner's earlier app (repository `AliG1111/PhoneLidar`, commit `1ac68a7`), whose build setup, conventions and remote link this app reuses.

## How to use these files

Section numbers (§1 … §12, §6.1 … §6.18) are stable and are cited across the repository (code comments, plan, reviews). Find a section's file in the index below and open only that file; a section number mentioned inside a file may live in another file.

## Summary

- **What.** A single-scene SwiftUI app (iOS 17+, iPhone only). A scanner phone mounted above an OSB forming line analyzes the strands ("flakes") in a user-drawn ROI at a user-set number of shots per second and reports their angle to the machine direction (MD); a second iPhone controls it over direct phone-to-phone Wi-Fi (the remote link ported from Phone LiDAR).
- **Principles** (§1): accuracy first (skip shots, never lower quality), know what each method measures, reproducible, reuse Phone LiDAR's validated setup, testable without a Mac.
- **Architecture** (§2–5): `ScanModel` → `CapturePipeline` on serial queues (data, session, analysis, run I/O, preview, remote link); measurement code is pure Swift on value types; `RunStore` and `RemoteLink` are `@Observable` main-actor objects.
- **Methods** (§6.4–6.5): *Flake edges* (LSD-style straight edges with collinear merging; default) and *Edge orientation* (structure tensor). Angles are averaged only as doubled angles (§6.6); MD comes from the mat's motion (§6.8).
- **Accuracy** (§6.12–6.13): a named error budget, validated on synthetic mats in the Python lab.
- **Light and scale** (§6.16–6.18): a light check at Start, readout-time test, LiDAR distance and scale, and a conditions forecast.
- **Data** (§7–9): crash-safe run folders with readable CSV/JSON; `Run.json` carries `formatVersion`; user-facing errors, never delete captured data.
- **Technology** (§10): native Swift/SwiftUI, AVFoundation, Accelerate, XcodeGen, GitHub Actions, Sideloadly or TestFlight.
- **Risks** (§11): R-01…R-20 (real mats vs synthetic, occlusion, lighting, rolling shutter, device facts, LiDAR distance).

## Index

| Sections | Topic | File |
|---|---|---|
| §1–2 | Scope, principles, architecture overview and module diagram | [01-scope-architecture.md](design/01-scope-architecture.md) |
| §3.1–3.8 | Modules: App, Capture, Motion, Analysis, Statistics, Scan/Runs/Library/Storage, Remote, Diagnostics and Target | [02-modules.md](design/02-modules.md) |
| §4–5 | Data flow; threading and concurrency | [03-dataflow-concurrency.md](design/03-dataflow-concurrency.md) |
| §6.1–6.8 | Angle convention, pre-processing, filters, both methods, axial statistics, histogram, motion and MD | [04-algorithms-core.md](design/04-algorithms-core.md) |
| §6.9–6.12 | Shot scheduler, capture settings and quality metrics, coverage, geometric error budget | [05-algorithms-capture.md](design/05-algorithms-capture.md) |
| §6.13 | Lab validation on synthetic mats (results of record) | [06-lab-validation.md](design/06-lab-validation.md) |
| §6.14–6.18 | Remote link extensions, test-target mode, light check and readout test, LiDAR distance and scale, conditions forecast | [07-remote-target-forecast.md](design/07-remote-target-forecast.md) |
| §7–9 | On-disk formats (run folder, `Run.json`, CSVs, summaries), storage layout, error handling | [08-formats-storage-errors.md](design/08-formats-storage-errors.md) |
| §10 | Technology recommendations and reuse of Phone LiDAR | [09-technology.md](design/09-technology.md) |
| §11–12 | Known limitations and design risks (R-xx), validation plan | [10-risks-validation.md](design/10-risks-validation.md) |
