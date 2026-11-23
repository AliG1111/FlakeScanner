# Flake-angle algorithm lab

Development tool, not part of the app. It renders synthetic strand mats with a known orientation distribution and measures how well candidate methods recover it, so design decisions and accuracy targets rest on numbers. From P1 it also exports a few small fixture images with reference results for the Swift parity tests (NFR-TST-02), and from P2 the printed test target.

## Run

```
pip install -r tools/lab/requirements.txt
python3 -I tools/lab/flake_lab.py                 # all experiments, 4 images per condition (about 10 minutes on 4 cores)
python3 -I tools/lab/flake_lab.py --quick         # 2 images per condition
python3 -I tools/lab/flake_lab.py --images 8      # images per condition
python3 -I tools/lab/flake_lab.py --only E9       # one experiment (repeat --only for more)
python3 -I tools/lab/flake_lab.py --save-example mat.png
```

Everything is seeded and deterministic. Errors are method minus truth, ± one standard error from the image-to-image scatter.

Results of record (8 images per condition, about 18 minutes; E4 alone about 8, E13 about 1.5):

```
python3 -I tools/lab/flake_lab.py --images 8 --json tools/lab/results-<date>.json | tee tools/lab/results-<date>.txt
```

## Model

- 768 × 768 px mats, 650 strands of 120 × 24 px (± 30 %), wood-grain streaks along each strand, 4× supersampled edges, optics blur 0.7 px, noise σ = 0.012.
- Orientation: axial von Mises with mean μ and concentration κ (κ = 4 ≈ 15° spread, face-layer-like; κ = 2 ≈ 24°; κ = 1 ≈ 36°; κ = 0 random).
- Truth: strands at least 25 % visible, counted once.
- Angles in image coordinates (x right, y down), 0° = +x = machine direction in the lab, so clockwise-positive on the screen. The app's flake angle is counter-clockwise-positive (design §6.1): θ = −β here. Flip the sign of lab means (not of spreads or percentages) before comparing them with app output; fixtures are exported in the app's convention.

## Methods compared

| Name | Method |
|---|---|
| `A_tensor` | Structure tensor (σ_d 1 px, σ_i = ¼ of the set flake width), weights coherence × energy |
| `A_tensor_coh` | Structure tensor, coherence ≥ 0.5, weight = coherence |
| `B_seg_count` | OpenCV LSD segments ≥ 1.5 × width, one sample per segment |
| `B_seg_len` | Same, length-weighted |
| `B_merged` | LSD pieces ≥ 10 px merged when collinear (≤ 3°, ≤ 1.5 px offset, gap ≤ 2 × width), then ≥ 1.5 × width — the app's default design |

OpenCV's LSD stands in for the app's own line-support-region detector (design §6.5); the app does not use OpenCV.

## Experiments

E1 bias vs mean direction · E2 spread vs concentration · E3 motion blur · E4 flicker banding: a control, short-period (40 px) and mid-period (300 px) PWM bands and mains-period bands, both sensor orientations, with and without normalization; then deep PWM bands (`pwm_gain`: a light on for a duty fraction of each period, seen through the exposure as trapezoidal bands, 135–1,000 rows) evaluated raw, row-corrected and with the proposed rules (`run_banding_condition`), with the banding detectors of `banding_metrics` printed for every condition · E5 one-sided light (shadows) · E6 strand aspect ratio · E7 mat density (occlusion) · E8 rotation bias: the same strands rotated, 3× images · E9 collinear merging vs density · E10 flake width set wrong · E11 flake-width estimate from paired edges · E12 ROI border rule (geometry only) · E13 light check, readout time and brightness drift (design §6.16) simulated at the row level: 2,160-row rolling-shutter frames under sine, rectified, phosphor/capacitor-smoothed, LED off-time and half-wave flicker, on still, shaking and moving surfaces; flicker index and frequency, readout time by the phase slope (and the earlier free-period fit for comparison), exposure and mains-offset effects, and the brightness drift at 1/30 s against 60.02 Hz mains.

`--images` sets the bursts per case in E13 too (2 with `--quick`, otherwise 4).

Results of record: [`results-2026-11-23.txt`](results-2026-11-23.txt) (and `.json`). Summary and conclusions: [design §6.13](../../docs/design.md#613-lab-validation-synthetic-mats).

## Rules

Synthetic images only. Never add plant photos, video, saved frames or run data to this folder or the repository.
