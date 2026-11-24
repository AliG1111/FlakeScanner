# Flake Scanner — Requirements (summary and index)

| | |
|---|---|
| Document | One-page summary and index of the requirements. The full text is split into per-topic files in [requirements/](requirements/). |
| Describes | The planned system (v1 = milestone M1, plus later phases). |
| Date | 2026-11-23 (split into per-topic files 2026-11-24, P0.9; text unchanged) |
| Companion documents | [design.md](design.md) (architecture, algorithms, formats, technology choices, risks), [implementation-plan.md](implementation-plan.md) (phases, model matrix, change log), [../CLAUDE.md](../CLAUDE.md) (agent rules), user guide [`../README.md`](../README.md) |

Requirements are written before the code. Each carries the phase that delivers it and a status; the traceability table is §9. Where a number is a proposed target it says so; the owner confirms or changes it (§8). The phase column of every requirement row is derived from the plan's task lines by `tools/docs/check_trace.py`, which reads all files in [requirements/](requirements/).

## How to use these files

Section numbers (§1 … §10) and requirement IDs (FR-xxx-nn, NFR-xxx-nn, CON-, ASM-, Q-) are stable. Find the file in the index below and open only that file; IDs are unique across files.

## Summary

- **Purpose** (§1): an iPhone app that measures the angle of OSB flakes to the machine direction on a moving mat and reports live and recorded statistics; a second iPhone controls it remotely; built and distributed without a Mac.
- **Context** (§2–4): camera directly overhead, line speed 100–1,000 mm/s, camera height measured by LiDAR, lighting varies by site; angle convention θ in (−90°, 90°], counter-clockwise from MD; axial statistics.
- **Functional** (§5): app shell, capture, ROI, analysis rate, direction and speed, two measurement methods, statistics, measurement quality, calibration and setup, runs and recording, library and export, remote link (groups FR-APP, FR-CAP, FR-ROI, FR-RATE, FR-DIR, FR-MEAS, FR-STAT, FR-QUAL, FR-CAL, FR-RUN, FR-LIB, FR-EXP, FR-RMT).
- **Non-functional** (§6): platform, measurement accuracy (NFR-ACC), performance, reliability and data integrity, storage, usability, maintainability and testability, security and privacy, build and distribution.
- **Constraints, assumptions, questions** (§7–8): CON-01…07, ASM-01…05, Q-01…Q-10 (several answered by the owner on 2026-11-23).
- **Traceability** (§9) and **document history** (§10).

## Index

| Sections | Topic | File |
|---|---|---|
| §1–4 | Purpose and scope, users and context, use cases, conventions (angle, statistics, other) | [01-scope-conventions.md](requirements/01-scope-conventions.md) |
| §5.1–5.6 | App shell, capture, ROI, analysis rate, machine direction and speed, measurement methods | [02-functional-core.md](requirements/02-functional-core.md) |
| §5.7–5.12 | Statistics, measurement quality, calibration and setup, runs and recording, library and export, remote link | [03-functional-results.md](requirements/03-functional-results.md) |
| §6 | Non-functional requirements (NFR-PLAT, ACC, PERF, REL, STO, USE, MNT/TST, SEC, BLD) | [04-nonfunctional.md](requirements/04-nonfunctional.md) |
| §7–8 | Constraints and assumptions, open questions | [05-constraints-questions.md](requirements/05-constraints-questions.md) |
| §9–10 | Traceability (groups to design sections, phases, tests), document history | [06-traceability-history.md](requirements/06-traceability-history.md) |
