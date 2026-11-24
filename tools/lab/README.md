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

Results of record (8 images per condition, E14 16; about 47 minutes on 4 cores; E4 alone about 30, of which the strand-direction grid about 5, the wide-strand map about 12 and the regime boundary about 5; E13 about 2, E14 about 2):

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

E1 bias vs mean direction · E2 spread vs concentration · E3 motion blur · E4 flicker banding: a control, short-period (40 px) and mid-period (300 px) PWM bands and mains-period bands, both sensor orientations, with and without normalization; then deep PWM bands (`pwm_gain`: a light on for a duty fraction of each period, seen through the exposure as trapezoidal bands, 135–1,000 rows) evaluated raw, row-corrected and with the banding rule (`banding_rule`, `run_banding_condition`), and the first part's sinusoidal and mains bands under the same rule, with the banding detectors of `banding_metrics` printed for every condition; the band metric `band_common` (the products of the row-profile differences of non-neighbouring strips) against the earlier `grad_frac` with the ROI narrowed to 768–256 px along the rows on mats without bands; the rule (`banding_rule`, `direction_regime`: B_merged excluded when band_common ≥ 0.0025, raw below; A_tensor raw below band_common 0.01, above it divided row by row (*rows*) when the set flake width w ≥ 30 px and the run's median angle ψ of the strands to the sensor rows (tensor on the row-corrected copy) is ≥ 50°, otherwise divided by its row means smoothed over 0.7 w rows, at most 25 (*along*), which excludes A when row_min < 0.5 or, for w ≥ 30 px, when band_common ≥ 0.04) and, for comparison, a strip-common correction (`strip_normalize8`, `banding_rule_strip`: each sensor row divided by the median over the six band_common strips of the strip's row mean over its mean, for both methods, on shots flagged at band_common ≥ 0.01, 0.005, 0.0025 or on every shot, with and without A's row_min 0.5 exclusion), each layer rendered once and seen under every band (`run_banding_layer`): layers at μ 20–90° (κ 4), κ 3, 2.5, 2, 1 and 0 and the other mount under sine, PWM and near-dark bands and two weak sine bands (40 and 135 rows, amplitude scaled per layer to a median band_common of about 0.0135), with the R distribution per κ; the wide-strand map (36 and 48 px, twice the images: ψ about every 10° at κ 4 in mount x, mount y, κ 2.5 at μ 30, 60 and 90, a random layer) under the same bands and a sine 40 band just below along's band_common limit; and the regime boundary (24 px, μ 40–60°, κ 2.5, 3 and 4); both methods in every section. Each band case shows A and B raw, under the rule and under strip-common at each threshold, with the rule's verdict under every regime the medians of 5-shot subsets pick (the app decides once per run from its first flagged shots). Each section ends with its verdict tally per method, the worst changes, the failing cases, the controls that false flags push outside the tolerances, and the clean-mat costs on the mean for every layer (control, every shot corrected: A rows / along / strip, B strip) with the false flags per threshold. The ROI-width part adds, per ROI width (768–256 px), the false flags at each threshold, the clean-mat cost of strip-common for both methods and a sine 40 band raw and strip-corrected · E5 one-sided light (shadows) · E6 strand aspect ratio · E7 mat density (occlusion) · E8 rotation bias: the same strands rotated, 3× images · E9 collinear merging vs density · E10 flake width set wrong · E11 flake-width estimate from paired edges · E12 ROI border rule (geometry only) · E13 light check, readout time and brightness drift (design §6.16) simulated at the row level: 2,160-row rolling-shutter frames under sine, rectified, phosphor/capacitor-smoothed, LED off-time and half-wave flicker, on still, shaking and moving surfaces; flicker index and frequency, readout time by the phase slope (and the earlier free-period fit for comparison), exposure and mains-offset effects, and the brightness drift at 1/30 s against 60.02 Hz mains; then the light check's frequency identification and acceptance (index ≥ 3× the median of the other bins and ≥ 0.01) for every case, the readout test's checks (readout time within 2 ms of the frame, amplitude ratio against (2/π) × index, weighted phase-fit residual, the mean of a normal and a 180°-turned run) on the valid cases with the error per readout gate, on kHz PWM (1,000–2,160 Hz) and on two lamps on other mains phases whose share changes across the frame, and the brightness drift at 1/30 s against 50.02 Hz mains for ROIs of 500 and 1,500 rows (reference = mean over the first second) · E14 image noise for the conditions forecast: white Gaussian noise σ 0.006–0.10 in steps of about √2 (0.006, 0.0085, 0.012, 0.017, 0.025, 0.035, 0.05, 0.071, 0.10) and a correlated variant (filtered with a 0.7 px Gaussian and rescaled, as ISP denoising leaves it) at every σ from 0.017, on face, core and random layers, twice the run's images per condition (each mat rendered once and seen at every σ), paired against the lab's baseline σ 0.012; contrast as the app will measure it (standard deviation after subtracting a Gaussian low-pass of 2 flake widths, on the noiseless image; the plain standard deviation for reference), CNR = that contrast / σ; B_merged's samples per image, band_common's false flags, the darkest row; and per layer and method the *Good* limit (smallest CNR up to which every change stays within half of the tolerances) and the *Poor* limit (within the tolerances), with fragile decisions (within one standard error of a threshold) marked, then the most conservative limits across layers.

`--images` sets the bursts per case in E13 too (2 with `--quick`, otherwise 4).

Results of record: [`results-2026-11-23.txt`](results-2026-11-23.txt) (and `.json`). Summary and conclusions: [design §6.13](../../docs/design.md#613-lab-validation-synthetic-mats).

## Rules

Synthetic images only. Never add plant photos, video, saved frames or run data to this folder or the repository.
