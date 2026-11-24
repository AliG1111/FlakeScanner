# Design: known limitations, design risks and validation plan (§11–12)

Part of the design ([summary](../design.md)). Section numbers are stable; cite them as §N.

## 11. Known limitations and design risks

| ID | Limitation / risk | Consequence | Mitigation / tracking |
|---|---|---|---|
| R-01 | Real mats differ from synthetic ones (irregular edges, fines, dust, colour, deeper occlusion). | Accuracy on the line is unknown until measured. | Sample media (Q-09); P8 V7 against hand-measured flakes; ML method (P10). |
| R-02 | Occlusion in dense mats. | Spread reads low and percent within limits high: about 1° for face-layer alignment, up to 2.6° in dense, weakly aligned mats (§6.12). | Collinear merging; P2.1 tuning; documented residual; P8 V7 on real flakes; ML (P10). |
| R-03 | Plant lighting: flicker and one-sided light. | PWM bands uncorrected up to 3.5° on the mean and 10° on the spread, bands with near-dark rows far more (lab E4); one-sided light about 2° on the mean (E5); mains flicker can change the brightness between frames. Banded shots are corrected (*Edge orientation*) or excluded (*Flake edges*, near-dark rows), so heavy banding costs shots rather than accuracy, but bands below the flags can still move angles by about 0.4–0.8° in the lab, and on layers along the rows the 0.0025 flag's false flags under steady light moved *Flake edges* by up to 0.33° in one check (§6.2); under banded light *Flake edges* alone measures little. | Common band gradient and darkest-row rules with the run's regime (§6.2), the forecast's *Light bands* factor (§6.18), light check and brightness drift; light and flicker measured by the device probe (P0.8); lighting guidance (a flicker-free LED, ASM-04); target test under the plant light (P8 V5). |
| R-04 | Fast line, little light. | Motion blur biases toward MD; high ISO adds noise. | Blur budget and exclusion; conditions forecast with remedies (§6.18); more light; torch. |
| R-05 | Rolling shutter. | Spread scaled and deviations from MD read about s too small or large, s ≈ 1–2 % (default mount, 1,000 mm/s, camera 1 m to 0.5 m above the mat, §6.12). | Mount guidance; s computed and recorded per run; P9 correction. |
| R-06 | Tilt, perspective, lens distortion. | Local errors toward the picture edges. | Level warning, centred ROI, distortion correction; P9 corrections. |
| R-07 | Heat on a hot mount during long runs. | Throttling, camera stop. | Thermal handling (NFR-PERF-05), USB-C power, lower rate. |
| R-08 | Analysis time at full resolution. | Lower achieved rate than requested. | Rate shown; profiling and Accelerate/Metal optimization (P8). |
| R-09 | Peer-to-peer Wi-Fi range at the line (steel, VFD noise). | Remote drops; the scanner is unaffected. | As Phone LiDAR R-18; travel router fallback. |
| R-10 | Pairing with a 6-digit code. | An attacker present at pairing could pair instead. | As Phone LiDAR R-19 (documented, owner decision). |
| R-11 | Free Apple ID signing lasts 7 days. | App stops opening on the plant floor. | TestFlight option. |
| R-12 | Remote code duplicated with Phone LiDAR. | Fixes must be made twice. | Shared package (backlog). |
| R-13 | No local compiler. | Slower iteration. | Pure-logic tests in CI, the Python lab, small PRs. |
| R-14 | The video image pipeline (denoise, sharpening, tone mapping, temporal noise reduction) may alter edges. | Unknown small bias or noise; in lab E14 noise smoothed as by noise reduction doubled *Edge orientation*'s contrast-to-noise limits and raised *Flake edges*' about 1.4 ×. | The probe measures the noise per ISO and its correlation (P0.8) and the forecast's limits follow it (§6.18); target test (P8); evaluate a still/RAW mode (10.3). |
| R-15 | Mount vibration. | Blur and MD noise. | Rigid mount; blur and drift checks. |
| R-16 | Assumptions not yet confirmed (requirements §8). | Defaults may be wrong. | Owner answers; settings are configurable. |
| R-17 | Public repository. | Exposure of plant data if committed. | Hygiene rules in `CLAUDE.md` and `.gitignore`. |
| R-18 | Flake width set wrong. | Set too narrow, flake ends count as edges and the spread reads several degrees too high (lab E10). | Required measured setting leaning wide, paired-edge cross-check, 12 px minimum (FR-CAL-07). |
| R-19 | Device facts assumed until measured: readout direction and time, binning, distortion correction with intrinsics, the video pipeline's processing, plant light and real flake images. | Rework of P1–P5 if found late. | Device probe build and plant visit before the measurement core (P0.7, P0.8). |
| R-20 | LiDAR distance: the run's format may not deliver depth, and the reading may be poor on the mat (dust, glare, an edge in the ROI). | Wrong scale (speeds, a rescaled flake width), or none. | Reading at Start by a short switch to the LiDAR camera, validity and spread checks, typed-in fallback (§6.17); tape-measure check in the probe (P0.8) and target check (P8 V3). |

## 12. Validation plan (summary)

Unit tests in CI (every PR) cover the pure logic: statistics against hand-computed values, rotation invariance (NFR-ACC-01), the estimators against the lab reference on its fixture images and against the truth of Swift-rendered mats (NFR-ACC-02, NFR-TST-02), synthetic motion (NFR-ACC-03), quality metrics on synthetic blur and banding, scheduler and coverage maths, target detection and matching, formats and repair, remote protocol, crypto and loopback. The device probe (P0.7, P0.8) measures the device facts the design assumes before the measurement core is built: formats, readout direction and time, the LiDAR distance, distortion correction with intrinsics, plant light and flicker, and real sample frames. On-device validation (P8, procedures written in P7) covers capture and analysis timing, MD against the printed bar, the printed target still (including the sign check) and moving, the real mat against hand-measured flakes, remote range and latency, a 60-minute run, kill and recovery.

