# Requirements: traceability and document history (§9–10)

Part of the requirements ([summary](../requirements.md)). Section numbers are stable; cite them as §N.

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
| 2026-11-23 | M0 review cycle 1 fixes ([reviews/2026-11-23-M0.md](../reviews/2026-11-23-M0.md)): accuracy targets per condition with error bars (NFR-ACC-02); required flake width (FR-CAL-07); diagnostics and device probe (FR-APP-06); test-target mode designed (FR-CAL-06); display range around the target and signed deviations (§4.1); capture settings fixed and recorded (FR-CAP-02/03, NFR-REL-04); rolling-shutter and tilt targets restated (NFR-ACC-06/07); light needed for the blur budget (ASM-04); MD change and absolute level (FR-DIR-04, FR-QUAL-06); scheduler, snapshots, *Both*, library timing, settings versioning; phase column derived from the plan's task lines. |
| 2026-11-23 | M0 review cycle 2 fixes ([reviews/2026-11-23-M0.md](../reviews/2026-11-23-M0.md), M0-22…M0-36): mains flicker found by a light check at 1/27 s plus a brightness-drift warning, since 1/30 s frames hide 60 Hz flicker (FR-QUAL-04, FR-APP-06); readout time fitted, s in pixels (NFR-ACC-07); moving test target referenced to the markers' track (FR-CAL-06, NFR-ACC-03/04); flake width stored with its camera and format, cross-check 0.75–2 × (FR-CAL-07); shots held through the MD-change confirmation (FR-DIR-04); skipped shots exclude stops (FR-RATE-02); the run being recorded is read-only (NFR-REL-02, FR-RUN-05/07, FR-LIB-04, FR-RMT-10); image counts fixed in advance (NFR-ACC-02). |
| 2026-11-23 | M0 review cycle 3 fixes ([reviews/2026-11-23-M0.md](../reviews/2026-11-23-M0.md), M0-37…M0-48): banding measured by band gradient and darkest row, with near-dark shots excluded and strong bands corrected (*Edge orientation*) or excluded (*Flake edges* across the readout) after deep PWM bands in lab E4 (FR-QUAL-04 a, FR-MEAS-04); brightness drift per strip with the exposure locked and the light check at Start (FR-QUAL-04 b, c); readout time from the phase slope of the flicker, lab E13 (NFR-ACC-07, FR-APP-06); a busy analysis no longer shifts the shot schedule, rates per moving time (FR-RATE-02); the MD-change hold sized from the MD window and the configured confirmation (FR-DIR-04); sharing only finished runs, recovery skips the current launch (FR-LIB-03, NFR-REL-02, FR-RUN-05). |
| 2026-11-23 | Owner's answers (Q-01 in part, Q-02, Q-04, Q-09) and a new requirement: the scanner phone has LiDAR; lighting varies by location; feedback when the results will be poor for the speed and the light (FR-QUAL-08, design §6.18, lab E14 planned for its noise thresholds); camera directly over the line; line speed 100–1,000 mm/s (ASM-03; shutter and light numbers in ASM-04 and FR-QUAL-03; rolling-shutter numbers in NFR-ACC-07); the camera height varies from mount to mount and is measured with the LiDAR at Start and in Setup (FR-CAL-02, design §6.17; FR-CAL-03 keeps only the perspective correction); a stored flake width is rescaled to a new camera distance (FR-CAL-07); no video yet, so synthetic images until the probe's frames. |
| 2026-11-24 | M0 review cycle 4 fixes ([reviews/2026-11-23-M0.md](../reviews/2026-11-23-M0.md), M0-49…M0-60): the banding rule keyed on the strands' direction to the sensor rows instead of MD against the readout, with a band metric that does not grow as the ROI narrows; *Flake edges* left out of banded shots and *Edge orientation* corrected in the run's regime, after lab E4 over strand directions, alignments and widths (FR-QUAL-04 a, FR-MEAS-04); the readout test as two bursts, the second turned 180°, with plausibility checks (FR-APP-06 c); the forecast's light limits as contrast-to-noise ratios from lab E14 and a *Light bands* factor (FR-QUAL-08, ASM-04); a run that stops with an error recovered in the same launch (NFR-REL-02, FR-RUN-05); the achieved-rate bound restated (FR-RATE-02). |
| 2026-11-24 | M0 review cycle 5 fixes ([reviews/2026-11-23-M0.md](../reviews/2026-11-23-M0.md), M0-61…M0-78): the banding regime of *Edge orientation* decided once per run from the strands' direction to the rows and the flake width, and *Flake edges* excluded from weak bands, after lab E4 over weak bands, the regime boundary and wide strands, with the residuals stated (FR-QUAL-04 a); the forecast's share of shots with light bands, its contrast and light limits restated from a refined E14, the highest expected speed a setting (FR-QUAL-08); the flake width's distance from a LiDAR reading taken when the width is set (FR-CAL-07, after the final review, M0-79…M0-86); the light the blur budget needs at the primary method's ISO limit (FR-QUAL-03, ASM-04). |

