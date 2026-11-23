#!/usr/bin/env python3
"""Flake-angle algorithm lab (development tool, not part of the app).

Renders synthetic strand mats with a known axial orientation distribution and
compares candidate estimators against the ground truth:

  A  structure tensor (texture / edge orientation field)
  B  straight-edge segments (OpenCV LSD here, as a stand-in for the app's own
     line-support-region detector), short segments removed; B_merged first
     joins collinear pieces of one edge split by crossing strands

Angles use image coordinates (x right, y down), 0 deg = +x = machine direction
(MD) in the lab, axial range (-90, 90]. Every run is deterministic (seeded).

Sign: lab angles are image angles beta, clockwise-positive on the screen. The
app's flake angle is theta = wrap(beta_MD - beta) (design 6.1), counter-clockwise-
positive; with the lab's MD at beta = 0 that is theta = -beta. Flip the sign of
lab means (not of spreads or percentages) before comparing them with app output.

Usage:
  python3 -I tools/lab/flake_lab.py              # all experiments, prints tables
  python3 -I tools/lab/flake_lab.py --quick      # 2 images per condition
  python3 -I tools/lab/flake_lab.py --images 8   # images per condition (default 4)
  python3 -I tools/lab/flake_lab.py --only E10   # selected experiments (repeatable)
  python3 -I tools/lab/flake_lab.py --save-example out.png

Results of record (see README.md), 8 images per condition, about 18 minutes:
  python3 -I tools/lab/flake_lab.py --images 8 --json tools/lab/results-<date>.json \
      | tee tools/lab/results-<date>.txt

Requires numpy and opencv-python-headless (see requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

import cv2
import numpy as np

SUPERSAMPLE = 4  # render at 4x and area-downsample, so edges are anti-aliased at every angle


# ----------------------------------------------------------------------------------------------
# Axial statistics
# ----------------------------------------------------------------------------------------------

def wrap_axial(deg):
    """Reduce angles (deg) to the axial range (-90, 90]."""
    d = (np.asarray(deg, dtype=np.float64) + 90.0) % 180.0 - 90.0
    return np.where(d <= -90.0, d + 180.0, d)


def axial_diff(a_deg, b_deg):
    """Smallest signed difference a - b of two axial angles (deg), in (-90, 90]."""
    return float(wrap_axial(a_deg - b_deg))


def axial_stats(theta_deg, weights=None, md_deg=0.0, within=(10.0, 20.0, 30.0)):
    """Doubled-angle statistics of axial data relative to `md_deg`."""
    th = wrap_axial(np.asarray(theta_deg, dtype=np.float64) - md_deg)
    w = np.ones_like(th) if weights is None else np.asarray(weights, dtype=np.float64)
    sw = float(w.sum())
    if th.size == 0 or sw <= 0:
        return {"n": 0}
    t2 = np.radians(2.0 * th)
    c = float((w * np.cos(t2)).sum() / sw)
    s = float((w * np.sin(t2)).sum() / sw)
    r = math.hypot(c, s)
    mean = math.degrees(math.atan2(s, c)) / 2.0
    sd = math.degrees(math.sqrt(-2.0 * math.log(max(r, 1e-12)))) / 2.0
    out = {"n": int(th.size), "mean": mean, "R": r, "sd": sd, "f": c,
           "mad": float((w * np.abs(th)).sum() / sw)}
    for lim in within:
        out[f"in{int(lim)}"] = float(100.0 * (w * (np.abs(th) <= lim)).sum() / sw)
    return out


def sample_axial_vonmises(rng, mu_deg, kappa, n):
    """Axial von Mises: the doubled angle is von Mises(2*mu, kappa); kappa <= 0 gives uniform."""
    if kappa <= 0:
        return rng.uniform(-90.0, 90.0, n)
    phi = rng.vonmises(math.radians(2.0 * mu_deg), kappa, n)
    return wrap_axial(np.degrees(phi) / 2.0)


# ----------------------------------------------------------------------------------------------
# Synthetic mat renderer
# ----------------------------------------------------------------------------------------------

def _poly_pts(corners, scale):
    # fillPoly with shift=4 gives 1/16 px vertex precision
    return np.round(np.asarray(corners) * scale * 16.0).astype(np.int32).reshape(-1, 1, 2)


def pwm_gain(size, period, duty, ramp, off=0.0, phase=None):
    """Row gain of a PWM-dimmed light seen through the rolling shutter, normalized to mean 1 over `size` rows.

    The light is on (level 1) for `duty` of each `period` rows of readout time and at `off` (0 = dark) for
    the rest; row y integrates it over the exposure, `ramp` = exposure / line time rows long, so the gain is
    the light's square wave seen through a box filter of `ramp` rows (trapezoidal bands, fully dark rows
    when the off time is longer than the exposure). phase (radians of the period) None puts the middle of
    a rising ramp (the steepest gain slope) at the image centre, as band_phase None does for the sinusoid.
    The mean-1 normalization stands in for auto exposure on the frame's mean brightness.
    """
    pos = np.arange(size, dtype=np.float64)
    on_len = duty * period
    x0 = size / 2.0 + ramp / 2.0 if phase is None else -phase / (2.0 * math.pi) * period

    def cum_on(x):                                  # on time in [x0, x], in rows, periodic
        u = x - x0
        return np.floor(u / period) * on_len + np.minimum(np.mod(u, period), on_len)

    if ramp > 0:
        frac = (cum_on(pos + ramp) - cum_on(pos)) / ramp
    else:
        frac = (np.mod(pos - x0, period) < on_len).astype(np.float64)
    g = off + (1.0 - off) * frac
    return (g / g.mean()).astype(np.float32)


def render_mat(rng, size=768, n=650, mu=0.0, kappa=4.0, length=120.0, width=24.0,
               grain=0.06, noise=0.012, psf=0.7, motion_blur=0.0, banding=0.0,
               band_period=40.0, band_axis="y", band_phase=None, shadow=None,
               banding_shape="sine", band_duty=0.5, band_ramp=64.0, band_off=0.0):
    """Render a mat of `n` strands; returns (8-bit image, truth dict).

    length/width are mean strand dimensions in output pixels (each strand +-30 %).
    motion_blur: box blur length in px along +x (MD) after optics.
    banding: relative amplitude of a sinusoidal gain along the sensor readout (flicker seen through the
        rolling shutter), e.g. 0.1; band_period in px. Sensor rows (lines of equal gain) run along x when
        band_axis is "y" (gain varies down the image: rows parallel to the lab's MD, travel across the
        readout) and along y when band_axis is "x" (gain varies along MD: the default mount, travel along
        the readout). band_phase None puts a zero crossing (steepest gain slope) at the image centre.
    banding_shape "pwm" replaces the sinusoid (banding is then ignored) by the deep, trapezoidal gain of a
        PWM-dimmed light (pwm_gain: on for band_duty of each band_period, band_off between pulses, box filter
        of band_ramp rows = exposure / line time), along the same axis.
    shadow: (dx, dy) px offset of a dark copy drawn under each strand (directional light).
    """
    ss = SUPERSAMPLE
    big = size * ss
    canvas = np.full((big, big), 0.30, np.float32)       # belt / background
    label = np.full((size, size), -1, np.int32)            # top-most strand per output pixel
    thetas = sample_axial_vonmises(rng, mu, kappa, n)
    lengths = length * rng.uniform(0.7, 1.3, n)
    widths = width * rng.uniform(0.7, 1.3, n)
    margin = 0.6 * length
    cxs = rng.uniform(-margin, size + margin, n)
    cys = rng.uniform(-margin, size + margin, n)
    shades = rng.uniform(0.45, 0.85, n)

    for i in range(n):
        th = math.radians(thetas[i])
        ux, uy = math.cos(th), math.sin(th)        # along the strand axis
        vx, vy = -uy, ux                            # across
        hl, hw = lengths[i] / 2.0, widths[i] / 2.0
        cx, cy = cxs[i], cys[i]
        corners = [(cx + sa * hl * ux + sb * hw * vx, cy + sa * hl * uy + sb * hw * vy)
                   for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        cpts = np.asarray(corners)
        x0 = max(int(math.floor(cpts[:, 0].min() * ss)) - 2, 0)
        x1 = min(int(math.ceil(cpts[:, 0].max() * ss)) + 2, big)
        y0 = max(int(math.floor(cpts[:, 1].min() * ss)) - 2, 0)
        y1 = min(int(math.ceil(cpts[:, 1].max() * ss)) + 2, big)
        if x1 <= x0 or y1 <= y0:
            continue

        if shadow is not None:
            sh = [(x + shadow[0], y + shadow[1]) for x, y in corners]
            sx0 = max(x0 - 16, 0)
            sy0 = max(y0 - 16, 0)
            sx1 = min(x1 + 16, big)
            sy1 = min(y1 + 16, big)
            smask = np.zeros((sy1 - sy0, sx1 - sx0), np.uint8)
            cv2.fillPoly(smask, [_poly_pts(np.asarray(sh) - [sx0 / ss, sy0 / ss], ss)], 1,
                         lineType=cv2.LINE_8, shift=4)
            canvas[sy0:sy1, sx0:sx1][smask > 0] *= 0.55

        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.fillPoly(mask, [_poly_pts(cpts - [x0 / ss, y0 / ss], ss)], 1, lineType=cv2.LINE_8, shift=4)
        sel = mask > 0
        if not sel.any():
            continue
        yy, xx = np.nonzero(sel)
        px = (xx + x0 + 0.5) / ss - cx
        py = (yy + y0 + 0.5) / ss - cy
        v = px * vx + py * vy                       # across coordinate (output px)
        u = px * ux + py * uy                       # along coordinate
        # Wood grain: streaks parallel to the strand axis (1-D noise across, slow variation along)
        knots = np.arange(-hw - 2.0, hw + 2.5, 0.5)
        prof = np.convolve(rng.normal(0.0, 1.0, knots.size), np.ones(3) / 3.0, mode="same")
        g = np.interp(v, knots, prof)
        along = 0.5 * np.sin(2.0 * math.pi * u / rng.uniform(40.0, 90.0) + rng.uniform(0, 6.3))
        canvas[y0:y1, x0:x1][sel] = shades[i] * (1.0 + grain * (g + along))

        cv2.fillPoly(label, [_poly_pts(cpts, 1)], int(i), lineType=cv2.LINE_8, shift=4)

    img = cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)
    if psf > 0:
        img = cv2.GaussianBlur(img, (0, 0), psf)
    if motion_blur > 0:
        k = int(round(motion_blur))
        if k >= 2:
            img = cv2.filter2D(img, -1, np.full((1, k), 1.0 / k, np.float32))
    if banding_shape == "pwm":
        gain = pwm_gain(size, band_period, band_duty, band_ramp, band_off, band_phase)
        img = img * (gain[:, None] if band_axis == "y" else gain[None, :])
    elif banding > 0:
        pos = np.arange(size, dtype=np.float32)
        phase = -2.0 * math.pi * (size / 2.0) / band_period if band_phase is None else band_phase
        gain = 1.0 + banding * np.sin(2.0 * math.pi * pos / band_period + phase)
        img = img * (gain[:, None] if band_axis == "y" else gain[None, :])
    img = img + rng.normal(0.0, noise, img.shape).astype(np.float32)
    img8 = np.clip(np.round(img * 255.0), 0, 255).astype(np.uint8)

    ids, counts = np.unique(label[label >= 0], return_counts=True)
    vis = np.zeros(n)
    vis[ids] = counts
    frac = vis / (lengths * widths)
    truth = {"theta": thetas, "visible_frac": frac, "length": lengths, "width": widths}
    return img8, truth


# ----------------------------------------------------------------------------------------------
# Estimators
# ----------------------------------------------------------------------------------------------

def _gauss_kernels(sigma):
    r = int(math.ceil(4.0 * sigma))
    x = np.arange(-r, r + 1, dtype=np.float64)
    g = np.exp(-0.5 * (x / sigma) ** 2)
    g /= g.sum()
    d = -x / sigma ** 2 * g
    d /= -(x * d).sum()                             # unit response to a unit ramp
    return g.astype(np.float32), d.astype(np.float32)


def structure_tensor(img8, sigma_d=1.0, sigma_i=6.0):
    img = img8.astype(np.float32) / 255.0
    g, d = _gauss_kernels(sigma_d)
    # sepFilter2D correlates; derivative sign is consistent for x and y, so Jxy keeps its sign.
    gx = cv2.sepFilter2D(img, cv2.CV_32F, d, g, borderType=cv2.BORDER_REFLECT)
    gy = cv2.sepFilter2D(img, cv2.CV_32F, g, d, borderType=cv2.BORDER_REFLECT)
    jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma_i)
    jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma_i)
    jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma_i)
    return jxx, jyy, jxy


def estimate_tensor(img8, sigma_d=1.0, sigma_i=6.0, coh_min=0.0, weight="energy*coh", border=None):
    jxx, jyy, jxy = structure_tensor(img8, sigma_d, sigma_i)
    step = max(1, int(round(sigma_i)))
    b = int(math.ceil(3 * sigma_i)) if border is None else border
    sl = (slice(b, -b, step), slice(b, -b, step))
    a, c, e = jxx[sl].ravel(), jyy[sl].ravel(), jxy[sl].ravel()
    tr = a + c
    mag = np.sqrt((a - c) ** 2 + 4.0 * e ** 2)
    coh = mag / np.maximum(tr, 1e-12)
    grad_dir = 0.5 * np.degrees(np.arctan2(2.0 * e, a - c))
    edge_dir = wrap_axial(grad_dir + 90.0)          # edges (and flake axes) are normal to the gradient
    if weight == "energy*coh":
        w = tr * coh
    elif weight == "coh":
        w = coh
    else:
        w = np.ones_like(coh)
    keep = coh >= coh_min
    return edge_dir[keep], w[keep]


def line_normalize8(img8, band_axis="y", window=0):
    """Divide out a per-sensor-row gain (flicker banding); returns 8-bit.

    Sensor rows run along x when band_axis is "y" and along y when it is "x" (see render_mat).
    window 0 divides every row by its own mean; window > 0 divides by a moving average of the row means
    over `window` rows, which removes only slow gain changes (mains flicker) and leaves the mat's own
    row-to-row variation alone.
    """
    img = img8.astype(np.float32)
    ax = 1 if band_axis == "y" else 0               # average along the row
    rm = img.mean(axis=ax)
    if window > 0:
        k = np.ones(int(window), np.float32) / float(window)
        pad = int(window) // 2
        rm = np.convolve(np.pad(rm, pad, mode="reflect"), k, mode="valid")[: rm.size]
    g = np.maximum(rm, 1.0) / float(rm.mean())
    out = img / (g[:, None] if band_axis == "y" else g[None, :])
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def _moving_average(p, window):
    """Moving average of a 1-D profile over `window` (odd) samples, reflected at the ends."""
    pad = int(window) // 2
    k = np.ones(int(window)) / float(window)
    return np.convolve(np.pad(p, pad, mode="reflect"), k, mode="valid")[: p.size]


def _peak_ratio(resid, pmin, pmax, harmonics=1):
    """Strongest narrow spectral peak of a detrended profile over its median spectral power.

    Hann window, power spectrum of the real FFT; the peak is searched over bins whose period lies in
    [pmin, pmax] rows. harmonics > 1 sums the power at the bin and its multiples up to that many (a
    harmonic-sum peak for trapezoidal bands, whose fundamental can lie outside the period range) and
    divides by the number of terms. The median runs over all bins but DC.
    """
    n = resid.size
    pw = np.abs(np.fft.rfft(resid * np.hanning(n))) ** 2
    med = float(np.median(pw[1:]))
    k = np.arange(pw.size)
    band = (k >= n / pmax) & (k <= n / pmin) & (k >= 1)
    best = 0.0
    for b in k[band]:
        idx = b * np.arange(1, harmonics + 1)
        idx = idx[idx < pw.size]
        best = max(best, float(pw[idx].sum()) / idx.size)
    return best / max(med, 1e-30)


def banding_metrics(img8, band_axis="y"):
    """Banding detectors on one shot (computed on the image before any correction).

    Sensor rows follow render_mat: rows run along x when band_axis is "y" (the row profile is the mean of
    each image row) and along y when it is "x". Returns:
      score        design 6.10: row profile minus its 129-row moving average, Hann-windowed FFT, strongest
                   bin with a period of 8-128 rows over the median power, divided by the same ratio of the
                   column profile
      score_long   the same with a 2nd-order polynomial detrend and periods of 8 rows to half the ROI height
      score_harm   score_long with the peak taken as a 4-harmonic sum (trapezoidal PWM bands)
      grad_frac    gradient energy of the bands relative to the image's: mean square of the row-to-row
                   difference of the row profile smoothed over 8 rows (the bands' slope; fine texture along the
                   rows averages out) over the mean square of the image's derivative along the readout
                   (Gaussian derivative, sigma 1 px, as the tensor's)
      row_min      minimum of the row profile smoothed over 8 rows / the profile's mean (near-dark rows: ~0)
      col_min      the same for the column profile (dark content shows in both)
    """
    img = img8.astype(np.float64)
    rows = img.mean(axis=1) if band_axis == "y" else img.mean(axis=0)
    cols = img.mean(axis=0) if band_axis == "y" else img.mean(axis=1)
    out = {}
    r129 = rows - _moving_average(rows, 129)
    c129 = cols - _moving_average(cols, 129)
    out["score"] = _peak_ratio(r129, 8.0, 128.0) / max(_peak_ratio(c129, 8.0, 128.0), 1e-30)

    def poly2(p):
        x = np.linspace(-1.0, 1.0, p.size)
        return p - np.polyval(np.polyfit(x, p, 2), x)
    rp, cp = poly2(rows), poly2(cols)
    out["score_long"] = _peak_ratio(rp, 8.0, rows.size / 2.0) / max(_peak_ratio(cp, 8.0, cols.size / 2.0), 1e-30)
    out["score_harm"] = (_peak_ratio(rp, 8.0, rows.size / 2.0, harmonics=4)
                         / max(_peak_ratio(cp, 8.0, cols.size / 2.0, harmonics=4), 1e-30))
    g, d = _gauss_kernels(1.0)
    f = img8.astype(np.float32)
    # derivative along the readout: down the image when band_axis is "y", along x when "x"
    dimg = cv2.sepFilter2D(f, cv2.CV_32F, g, d) if band_axis == "y" else cv2.sepFilter2D(f, cv2.CV_32F, d, g)
    drow = np.diff(np.convolve(rows, np.ones(8) / 8.0, mode="valid"))
    out["grad_frac"] = float(np.mean(drow ** 2) / max(float(np.mean(dimg.astype(np.float64) ** 2)), 1e-12))

    def depth(p):
        sm = np.convolve(p, np.ones(8) / 8.0, mode="valid")
        return float(sm.min() / max(float(p.mean()), 1e-12))
    out["row_min"] = depth(rows)
    out["col_min"] = depth(cols)
    return out


_LSD = None


def estimate_segments(img8, min_len=36.0):
    global _LSD
    if _LSD is None:
        _LSD = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = _LSD.detect(img8)[0]
    if lines is None:
        return np.zeros(0), np.zeros(0)
    l = lines.reshape(-1, 4).astype(np.float64)
    dx, dy = l[:, 2] - l[:, 0], l[:, 3] - l[:, 1]
    ln = np.hypot(dx, dy)
    keep = ln >= min_len
    return wrap_axial(np.degrees(np.arctan2(dy[keep], dx[keep]))), ln[keep]


def _segments_raw(img8, min_len):
    global _LSD
    if _LSD is None:
        _LSD = cv2.createLineSegmentDetector(cv2.LSD_REFINE_STD)
    lines = _LSD.detect(img8)[0]
    if lines is None:
        return np.zeros((0, 4))
    l = lines.reshape(-1, 4).astype(np.float64)
    ln = np.hypot(l[:, 2] - l[:, 0], l[:, 3] - l[:, 1])
    return l[ln >= min_len]


def merge_collinear(l, max_angle=3.0, max_offset=1.5, max_gap=48.0):
    """Merge pieces of one straight edge interrupted by crossing strands (union-find over pairs).

    Two pieces join when their axial angles differ by <= max_angle deg, every endpoint of each lies
    within max_offset px of the other's line, and the gap between them along the line is <= max_gap px.
    Returns merged segments as (angle_deg, length_px) arrays.
    """
    n = len(l)
    if n == 0:
        return np.zeros(0), np.zeros(0)
    p1, p2 = l[:, :2], l[:, 2:]
    d = p2 - p1
    ln = np.hypot(d[:, 0], d[:, 1])
    u = d / ln[:, None]
    nrm = np.stack([-u[:, 1], u[:, 0]], axis=1)
    ang = np.degrees(np.arctan2(u[:, 1], u[:, 0]))
    da = np.abs(wrap_axial(ang[:, None] - ang[None, :]))
    # offsets of j's endpoints from line i
    o1 = np.abs(((p1[None, :, :] - p1[:, None, :]) * nrm[:, None, :]).sum(-1))
    o2 = np.abs(((p2[None, :, :] - p1[:, None, :]) * nrm[:, None, :]).sum(-1))
    t1 = ((p1[None, :, :] - p1[:, None, :]) * u[:, None, :]).sum(-1)
    t2 = ((p2[None, :, :] - p1[:, None, :]) * u[:, None, :]).sum(-1)
    tmin, tmax = np.minimum(t1, t2), np.maximum(t1, t2)
    gap = np.maximum(0.0, np.maximum(tmin - ln[:, None], -tmax))
    ok = (da <= max_angle) & (o1 <= max_offset) & (o2 <= max_offset) & (gap <= max_gap)
    ok = ok & ok.T
    parent = np.arange(n)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    ii, jj = np.nonzero(np.triu(ok, 1))
    for a, b in zip(ii, jj):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    roots = np.array([find(a) for a in range(n)])
    out_a, out_l = [], []
    for r in np.unique(roots):
        m = roots == r
        w = ln[m]
        t2a = np.radians(2.0 * ang[m])
        mean = 0.5 * math.atan2((w * np.sin(t2a)).sum(), (w * np.cos(t2a)).sum())
        e = np.array([math.cos(mean), math.sin(mean)])
        pts = np.concatenate([p1[m], p2[m]])
        proj = pts @ e
        out_a.append(math.degrees(mean))
        out_l.append(float(proj.max() - proj.min()))
    return wrap_axial(np.array(out_a)), np.array(out_l)


def estimate_segments_merged(img8, min_len=36.0, piece_min=10.0, max_gap=48.0):
    l = _segments_raw(img8, piece_min)
    a, ln = merge_collinear(l, max_gap=max_gap)
    keep = ln >= min_len
    return a[keep], ln[keep]


def estimate_width_paired(img8, piece_min=10.0, max_angle=4.0, min_overlap=0.5, wmin=3.0, wmax=150.0):
    """Typical flake width (px) from the two long sides of single flakes.

    LSD orients every segment so that the brighter side lies at cross(u, p - m) < 0 (image y down),
    so the two long sides of a bright flake are anti-parallel with each other's bright side facing
    inwards. For each edge, the nearest anti-parallel edge (within max_angle) on its bright side whose
    projections overlap by >= min_overlap of the shorter piece, and which in turn has the first edge on
    its own bright side, is its partner; their distance is one width sample. Returns the length-weighted
    median of the samples and their count (median of a +-30 % uniform width spread = its mean).
    """
    l = _segments_raw(img8, piece_min)
    n = len(l)
    if n < 2:
        return float("nan"), 0
    p1, p2 = l[:, :2], l[:, 2:]
    d = p2 - p1
    ln = np.hypot(d[:, 0], d[:, 1])
    u = d / ln[:, None]
    g = np.stack([u[:, 1], -u[:, 0]], axis=1)       # unit normal towards the bright side
    m = 0.5 * (p1 + p2)
    anti = (u @ u.T) <= -math.cos(math.radians(max_angle))
    rel = m[None, :, :] - m[:, None, :]             # m_j - m_i
    dist = (rel * g[:, None, :]).sum(-1)            # j's offset along i's bright normal
    mutual = (dist > wmin) & (dist.T > wmin) & (dist < wmax)
    # overlap of j's projection with i's extent along u_i
    t1 = ((p1[None, :, :] - p1[:, None, :]) * u[:, None, :]).sum(-1)
    t2 = ((p2[None, :, :] - p1[:, None, :]) * u[:, None, :]).sum(-1)
    lo = np.maximum(0.0, np.minimum(t1, t2))
    hi = np.minimum(ln[:, None], np.maximum(t1, t2))
    ov = np.maximum(0.0, hi - lo)
    ok = anti & mutual & (ov >= min_overlap * np.minimum(ln[:, None], ln[None, :]))
    dd = np.where(ok, dist, np.inf)
    j = np.argmin(dd, axis=1)
    has = np.isfinite(dd[np.arange(n), j])
    if not has.any():
        return float("nan"), 0
    samples = dd[np.arange(n), j][has]
    weights = ov[np.arange(n), j][has]
    order = np.argsort(samples)
    cw = np.cumsum(weights[order])
    med = float(samples[order][np.searchsorted(cw, 0.5 * cw[-1])])
    return med, int(has.sum())


# ----------------------------------------------------------------------------------------------
# Experiments
# ----------------------------------------------------------------------------------------------

METHODS = ("A_tensor", "A_tensor_coh", "B_seg_count", "B_seg_len", "B_merged")


def run_condition(seed, images, width_set=None, normalize=None, probe=None, **mat):
    """Pool estimates over `images` mats (all drawn from one seeded generator).

    Returns per-method pooled statistics, the pooled truth (strands >= 25 % visible), and for each method
    the standard error of its error (mean, sd, in20) from the image-to-image scatter.
    width_set: expected flake width the estimators assume (default: the true mean width).
    normalize: None, "line" (divide every sensor row by its mean) or ("smooth", window) (divide by a moving
        average of the row means); sensor rows follow mat["band_axis"].
    probe: optional function (raw 8-bit image, band_axis) -> dict, called on each image before any
        normalization; the results go to out["_probe"] and the per-image errors to out["_err"]. It draws no
        random numbers, so the other results do not change.
    """
    rng = np.random.default_rng(seed)
    wset = float(width_set if width_set is not None else mat.get("width", 24.0))
    axis = mat.get("band_axis", "y")
    pools = {k: ([], []) for k in ("truth",) + METHODS}
    errs = {k: [] for k in METHODS}
    timing = {"A": 0.0, "B_merged": 0.0}
    probes = []
    for _ in range(images):
        img, truth = render_mat(rng, **mat)
        if probe is not None:
            probes.append(probe(img, axis))
        if normalize == "line":
            img = line_normalize8(img, axis)
        elif isinstance(normalize, tuple) and normalize[0] == "smooth":
            img = line_normalize8(img, axis, window=normalize[1])
        tth = truth["theta"][truth["visible_frac"] >= 0.25]
        est = {}
        t0 = time.perf_counter()
        est["A_tensor"] = estimate_tensor(img, sigma_i=0.25 * wset)
        timing["A"] += time.perf_counter() - t0
        est["A_tensor_coh"] = estimate_tensor(img, sigma_i=0.25 * wset, coh_min=0.5, weight="coh")
        ths, ln = estimate_segments(img, min_len=1.5 * wset)
        est["B_seg_count"] = (ths, None)
        est["B_seg_len"] = (ths, ln)
        t0 = time.perf_counter()
        thm, _ = estimate_segments_merged(img, min_len=1.5 * wset, max_gap=2.0 * wset)
        timing["B_merged"] += time.perf_counter() - t0
        est["B_merged"] = (thm, None)
        pools["truth"][0].append(tth)
        ts = axial_stats(tth)
        for k in METHODS:
            th, w = est[k]
            pools[k][0].append(th)
            pools[k][1].append(np.ones_like(th) if w is None else w)
            ms = axial_stats(th, w)
            if ms.get("n", 0) and ts.get("n", 0):
                errs[k].append((axial_diff(ms["mean"], ts["mean"]), ms["sd"] - ts["sd"], ms["in20"] - ts["in20"]))
    out = {"truth": axial_stats(np.concatenate(pools["truth"][0]))}
    for k in METHODS:
        th = np.concatenate(pools[k][0])
        w = np.concatenate(pools[k][1])
        out[k] = axial_stats(th, w)
        e = np.asarray(errs[k])
        if len(e) >= 2:
            se = e.std(axis=0, ddof=1) / math.sqrt(len(e))
            out[k]["se"] = {"mean": float(se[0]), "sd": float(se[1]), "in20": float(se[2])}
    out["_timing_ms"] = {k: 1000.0 * v / images for k, v in timing.items()}
    if probe is not None:
        out["_probe"] = probes
        out["_err"] = {k: [list(e) for e in errs[k]] for k in METHODS}
    return out


BANDING_METHODS = ("A_tensor", "B_merged")
BAND_DARK_MIN = 0.15    # proposed: exclude a shot (both methods) whose row_min is below this (near-dark rows)
BAND_GRAD_MIN = 0.03    # proposed: banding that matters when grad_frac >= this
BAND_SMOOTH_ACROSS = 17  # proposed: rows over which the row means are smoothed for the correction across the readout


def run_banding_condition(seed, images, dark_min=BAND_DARK_MIN, grad_min=BAND_GRAD_MIN, **mat):
    """E4-style condition evaluated three ways on the same images, A_tensor and B_merged only (estimator
    settings of run_condition, so "raw" equals run_condition's result for the same seed and mat):
      raw   as rendered
      line  every sensor row divided by its mean (line_normalize8), on every image
      rule  the proposed rules: a shot with row_min < dark_min is excluded (both methods); otherwise, when
            grad_frac >= grad_min, A_tensor is row-corrected (default mount, band_axis "x": every row divided
            by its mean; rows along MD, "y": divided by the row means smoothed over BAND_SMOOTH_ACROSS rows,
            because per-row division also removes the strands' own row structure there) and B_merged is
            used uncorrected in the default mount and excluded in the other
    Returns {variant: {method: pooled stats with "se"}, "truth": ..., "_probe": [banding_metrics per image],
    "_probe_other": [the same with the other band_axis], "_err": {variant: {method: [(mean err, sd err, in20
    err) per image, None for an excluded shot]}}, "_rule": {"excluded": shots excluded for dark rows,
    "flagged": shots with grad_frac >= grad_min}}.
    """
    rng = np.random.default_rng(seed)
    wset = float(mat.get("width", 24.0))
    axis = mat.get("band_axis", "y")
    variants = ("raw", "line", "rule")
    pools = {v: {m: [] for m in BANDING_METHODS} for v in variants}
    errs = {v: {m: [] for m in BANDING_METHODS} for v in variants}
    truth_pool, probes, probes_other = [], [], []
    rule_truth = {m: [] for m in BANDING_METHODS}
    excluded = flagged = 0
    for _ in range(images):
        img, truth = render_mat(rng, **mat)
        met = banding_metrics(img, axis)
        probes.append(met)
        probes_other.append(banding_metrics(img, "x" if axis == "y" else "y"))
        tth = truth["theta"][truth["visible_frac"] >= 0.25]
        truth_pool.append(tth)
        ts = axial_stats(tth)
        est = {}
        for v, im in (("raw", img), ("line", line_normalize8(img, axis))):
            est[v] = {"A_tensor": estimate_tensor(im, sigma_i=0.25 * wset),
                      "B_merged": (estimate_segments_merged(im, min_len=1.5 * wset, max_gap=2.0 * wset)[0], None)}
        if met["row_min"] < dark_min:
            excluded += 1
            est["rule"] = {"A_tensor": None, "B_merged": None}
        elif met["grad_frac"] >= grad_min:
            flagged += 1
            if axis == "x":
                est["rule"] = {"A_tensor": est["line"]["A_tensor"], "B_merged": est["raw"]["B_merged"]}
            else:
                sm = line_normalize8(img, axis, window=BAND_SMOOTH_ACROSS)
                est["rule"] = {"A_tensor": estimate_tensor(sm, sigma_i=0.25 * wset), "B_merged": None}
        else:
            est["rule"] = est["raw"]
        for m in BANDING_METHODS:
            if est["rule"][m] is not None:
                rule_truth[m].append(tth)
        for v in variants:
            for m in BANDING_METHODS:
                if est[v][m] is None:
                    errs[v][m].append(None)
                    continue
                th, w = est[v][m]
                pools[v][m].append((th, np.ones_like(th) if w is None else w))
                ms = axial_stats(th, w)
                errs[v][m].append((axial_diff(ms["mean"], ts["mean"]), ms["sd"] - ts["sd"], ms["in20"] - ts["in20"])
                                  if ms.get("n", 0) and ts.get("n", 0) else None)
    out = {"truth": axial_stats(np.concatenate(truth_pool)), "_probe": probes, "_probe_other": probes_other,
           "_rule": {"excluded": excluded, "flagged": flagged},
           "_err": {v: {m: [None if e is None else list(e) for e in errs[v][m]] for m in BANDING_METHODS}
                    for v in variants}}
    for v in variants:
        out[v] = {}
        for m in BANDING_METHODS:
            tr = out["truth"] if v != "rule" else (axial_stats(np.concatenate(rule_truth[m])) if rule_truth[m]
                                                   else {"n": 0})
            if not pools[v][m]:
                out[v][m] = {"n": 0}
                continue
            th = np.concatenate([a for a, _ in pools[v][m]])
            w = np.concatenate([b for _, b in pools[v][m]])
            st = axial_stats(th, w)
            e = np.asarray([x for x in errs[v][m] if x is not None])
            if len(e) >= 2:
                se = e.std(axis=0, ddof=1) / math.sqrt(len(e))
                st["se"] = {"mean": float(se[0]), "sd": float(se[1]), "in20": float(se[2])}
            st["err_mean"] = axial_diff(st["mean"], tr["mean"]) if tr.get("n", 0) else float("nan")
            st["err_sd"] = st["sd"] - tr["sd"] if tr.get("n", 0) else float("nan")
            out[v][m] = st
    return out


def fmt_row(name, s, truth=None):
    if s.get("n", 0) == 0:
        return f"  {name:<14} n=0"
    t = ""
    if truth is not None:
        se = s.get("se", {"mean": float("nan"), "sd": float("nan"), "in20": float("nan")})
        t = (f"  | err mean {axial_diff(s['mean'], truth['mean']):+6.2f}±{se['mean']:.2f}"
             f"  sd {s['sd'] - truth['sd']:+6.2f}±{se['sd']:.2f}"
             f"  in20 {s['in20'] - truth['in20']:+6.1f}±{se['in20']:.1f}  f {s['f'] - truth['f']:+.3f}")
    return (f"  {name:<14} n={s['n']:>7}  mean {s['mean']:+7.2f}  sd {s['sd']:6.2f}  R {s['R']:.3f}"
            f"  f {s['f']:+.3f}  in20 {s['in20']:5.1f}%  mad {s['mad']:5.2f}{t}")


def report(title, res, methods=METHODS):
    print(title)
    tr = res["truth"]
    print(fmt_row("truth", tr))
    for m in methods:
        print(fmt_row(m, res[m], tr))
    print(f"  time per 768x768 image (Python/OpenCV, this PC): A (one tensor) {res['_timing_ms']['A']:.0f} ms,"
          f" B_merged (detect + merge) {res['_timing_ms']['B_merged']:.0f} ms")


def mean_errors(r):
    tr = r["truth"]
    return "  ".join(f"{m} {axial_diff(r[m]['mean'], tr['mean']):+5.2f}±{r[m].get('se', {}).get('mean', float('nan')):.2f}"
                     for m in METHODS)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="2 images per condition")
    ap.add_argument("--images", type=int, default=4, help="images per condition (default 4)")
    ap.add_argument("--save-example", metavar="PNG", help="write one synthetic mat and exit")
    ap.add_argument("--json", metavar="FILE", help="also write all results as JSON")
    ap.add_argument("--only", metavar="E", action="append",
                    help="run only these experiments (E1..E13); repeatable")
    args = ap.parse_args(argv)
    images = 2 if args.quick else max(2, args.images)

    if args.save_example:
        img, _ = render_mat(np.random.default_rng(1), mu=10.0, kappa=4.0)
        cv2.imwrite(args.save_example, img)
        return 0

    print(f"Flake lab: {images} images per condition (E8: 3x). Errors are method minus truth, ± one standard"
          " error from the image-to-image scatter. Angles: lab image angles (clockwise-positive).")
    results = {"_images": images}
    experiments = (("E1", experiment_e1), ("E2", experiment_e2), ("E3", experiment_e3), ("E4", experiment_e4),
                   ("E5", experiment_e5), ("E6", experiment_e6), ("E7", experiment_e7), ("E8", experiment_e8),
                   ("E9", experiment_e9), ("E10", experiment_e10), ("E11", experiment_e11),
                   ("E12", experiment_e12), ("E13", experiment_e13))
    for name, fn in experiments:
        if not args.only or name in args.only:
            fn(images, results)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, default=float)
    return 0


def experiment_e1(images, results):
    print("\nE1  Mean-angle bias vs true mean direction (kappa 4, aspect 5:1)")
    for mu in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0):
        r = run_condition(100 + int(mu), images, mu=mu, kappa=4.0)
        results[f"E1_mu{int(mu)}"] = r
        print(f"  mu {mu:4.0f}: truth mean {r['truth']['mean']:+6.2f}  errors: {mean_errors(r)}")


def experiment_e2(images, results):
    print("\nE2  Spread vs concentration (mu 0)")
    for kappa in (0.0, 1.0, 2.0, 4.0, 8.0):
        r = run_condition(200 + int(kappa * 10), images, mu=0.0, kappa=kappa)
        results[f"E2_k{kappa}"] = r
        report(f" kappa {kappa}", r)


def experiment_e3(images, results):
    print("\nE3  Motion blur along MD (mu 10, kappa 4, same strands in every row)")
    for mb in (0.0, 2.0, 4.0, 8.0):
        r = run_condition(300, images, mu=10.0, kappa=4.0, motion_blur=mb)
        results[f"E3_blur{int(mb)}"] = r
        report(f" blur {mb:.0f} px", r)


def experiment_e4(images, results):
    print("\nE4  Flicker banding through the rolling shutter (mu 10, kappa 4; same strands and noise in every row)")
    print("    rows across MD = default mount (travel along the readout); rows along MD = travel across it.")
    print("    40 px ~ kHz PWM dimming; 300 px ~ 0.5-1 kHz PWM; 1100-2700 px ~ 100/120 Hz mains flicker at 8-16 ms readout.")
    conds = (
        ("control, no banding", {}, None),
        ("PWM 40 px 10 %, rows along MD", dict(banding=0.10, band_period=40.0, band_axis="y"), None),
        ("  same + line normalization", dict(banding=0.10, band_period=40.0, band_axis="y"), "line"),
        ("PWM 40 px 10 %, rows across MD", dict(banding=0.10, band_period=40.0, band_axis="x"), None),
        ("  same + line normalization", dict(banding=0.10, band_period=40.0, band_axis="x"), "line"),
        ("mains 1100 px 30 %, rows across MD", dict(banding=0.30, band_period=1100.0, band_axis="x"), None),
        ("  same + smooth normalization 129", dict(banding=0.30, band_period=1100.0, band_axis="x"), ("smooth", 129)),
        ("mains 2700 px 30 %, rows across MD", dict(banding=0.30, band_period=2700.0, band_axis="x"), None),
        ("mains 1100 px 30 %, rows along MD", dict(banding=0.30, band_period=1100.0, band_axis="y"), None),
        ("PWM 300 px 10 %, rows across MD", dict(banding=0.10, band_period=300.0, band_axis="x"), None),
        ("  same + line normalization", dict(banding=0.10, band_period=300.0, band_axis="x"), "line"),
        ("PWM 300 px 10 %, rows along MD", dict(banding=0.10, band_period=300.0, band_axis="y"), None),
        ("  same + line normalization", dict(banding=0.10, band_period=300.0, band_axis="y"), "line"),
    )
    ctrl_err = None
    for i, (name, kw, norm) in enumerate(conds):
        r = run_condition(400, images, normalize=norm, probe=banding_metrics, mu=10.0, kappa=4.0, **kw)
        results[f"E4_{i}"] = dict(r, _label=name)
        report(f" {name}", r)
        if ctrl_err is None:
            ctrl_err = r["_err"]
        print("    vs control (paired, per image): " + "  ".join(
            f"{m} {_paired_text(r['_err'][m], ctrl_err[m])}" for m in BANDING_METHODS))
        print(_detect_text(r["_probe"]))
    experiment_e4_pwm(images, results)


def _paired_text(errs, ctrl):
    """Mean +- SE over images of (condition error - control error) for the mean and the spread (deg)."""
    out = []
    for j, lab in ((0, "mean"), (1, "sd")):
        d = np.asarray([e[j] - c[j] for e, c in zip(errs, ctrl) if e is not None and c is not None])
        if d.size == 0:
            out.append(f"{lab}   excluded")
        elif d.size == 1:
            out.append(f"{lab} {d[0]:+6.2f}")
        else:
            out.append(f"{lab} {d.mean():+6.2f}±{d.std(ddof=1) / math.sqrt(d.size):.2f}")
    return " ".join(out)


def _detect_text(probes, keys=("score", "score_long", "score_harm", "grad_frac", "row_min", "col_min")):
    return "    detect (median [min, max] over images): " + "  ".join(
        f"{k} {np.median([p[k] for p in probes]):.3g} [{min(p[k] for p in probes):.3g},"
        f" {max(p[k] for p in probes):.3g}]" for k in keys)


# Deep PWM bands: (period rows, duty, ramp rows, off level, mounts)
E4_PWM = (
    (135.0, 0.5, 64.0, 0.0, "x"), (135.0, 0.8, 64.0, 0.0, "xy"), (135.0, 0.9, 64.0, 0.0, "xy"),
    (135.0, 0.8, 128.0, 0.0, "x"),
    (270.0, 0.5, 64.0, 0.0, "xy"), (270.0, 0.8, 64.0, 0.0, "xy"), (270.0, 0.9, 64.0, 0.0, "xy"),
    (270.0, 0.8, 128.0, 0.0, "xy"),
    (270.0, 0.5, 64.0, 0.05, "x"), (270.0, 0.5, 64.0, 0.10, "x"), (270.0, 0.5, 64.0, 0.20, "x"),
    (540.0, 0.5, 64.0, 0.0, "x"), (540.0, 0.8, 64.0, 0.0, "xy"), (540.0, 0.9, 64.0, 0.0, "xy"),
    (540.0, 0.8, 128.0, 0.0, "xy"),
    (1000.0, 0.8, 64.0, 0.0, "x"), (1000.0, 0.9, 128.0, 0.0, "xy"),
)

# The first part's sinusoidal bands under the same rules: (name, render arguments, mounts)
E4_RULE_SINE = (
    ("sine 40 rows 10 %", dict(banding=0.10, band_period=40.0), "xy"),
    ("sine 300 rows 10 %", dict(banding=0.10, band_period=300.0), "xy"),
    ("mains 1100 rows 30 %", dict(banding=0.30, band_period=1100.0), "xy"),
    ("mains 2700 rows 30 %", dict(banding=0.30, band_period=2700.0), "x"),
)


def _print_rule_condition(name, r, ctrl_raw_err, images):
    """One run_banding_condition result as raw / line / rule changes from the control, plus the detectors."""
    print(f" {name}")
    for v in ("raw", "line", "rule"):
        extra = (f" (dark rows: excluded {r['_rule']['excluded']}/{images}; grad_frac flagged"
                 f" {r['_rule']['flagged']})" if v == "rule" else "")
        print(f"    {v:<4}" + "  ".join(f"  {m} {_paired_text(r['_err'][v][m], ctrl_raw_err[m])}"
                                      for m in BANDING_METHODS) + extra)
    print(_detect_text(r["_probe"]))


def experiment_e4_pwm(images, results):
    print("\nE4  (cont.) Deep PWM bands: a light on for `duty` of each period (off level 0 unless given), each row"
          " integrating it over\n    the exposure = `ramp` rows (64 rows ~ 1/4,200 s at an 8 ms readout of"
          " 2,160 rows; 128 rows ~ 16 ms), gain normalized to mean 1.\n    Same mats as above (mu 10, kappa"
          " 4). x = rows across MD (default mount), y = rows along MD. Changes from the control, mean ± SE over"
          "\n    the images of the paired difference (deg): raw; line = every sensor row divided by its mean;"
          f" rule = shots with row_min < {BAND_DARK_MIN}\n    excluded; when grad_frac >= {BAND_GRAD_MIN}:"
          " A_tensor row-corrected (mount x: per row; mount y: row means smoothed over"
          f" {BAND_SMOOTH_ACROSS} rows),\n    B_merged kept in mount x and excluded in mount y. Harmful: |mean|"
          " > 0.25 or |sd| > 0.5.")
    ctrl = {}
    for ax in ("x", "y"):
        r = run_banding_condition(400, images, mu=10.0, kappa=4.0, band_axis=ax)
        ctrl[ax] = r
        results[f"E4_pwm_control_{ax}"] = dict(r, _label=f"control, no banding, sensor rows {ax}")
        print(f" control, no banding, mount {ax}: raw A_tensor err mean {r['raw']['A_tensor']['err_mean']:+.2f}"
              f" sd {r['raw']['A_tensor']['err_sd']:+.2f}, B_merged err mean {r['raw']['B_merged']['err_mean']:+.2f}"
              f" sd {r['raw']['B_merged']['err_sd']:+.2f} | line vs raw: " + "  ".join(
                  f"{m} {_paired_text(r['_err']['line'][m], r['_err']['raw'][m])}" for m in BANDING_METHODS)
              + f" | rule: excluded {r['_rule']['excluded']}, flagged {r['_rule']['flagged']}")
        print(_detect_text(r["_probe"]))
    for period, duty, ramp, off, mounts in E4_PWM:
        g = pwm_gain(768, period, duty, ramp, off)
        for ax in mounts:
            r = run_banding_condition(400, images, mu=10.0, kappa=4.0, band_axis=ax, banding_shape="pwm",
                                      band_period=period, band_duty=duty, band_ramp=ramp, band_off=off)
            name = (f"PWM {period:.0f} rows, duty {duty}, ramp {ramp:.0f}" + (f", off {off}" if off else "")
                    + f", mount {ax} (gain {g.min():.2f}-{g.max():.2f})")
            results[f"E4_pwm_{period:.0f}_{duty}_{ramp:.0f}_{off}_{ax}"] = dict(r, _label=name)
            _print_rule_condition(name, r, ctrl[ax]["_err"]["raw"], images)
    print(" The first part's sinusoidal and mains bands under the same rules (same mats and seed):")
    for label, kw, mounts in E4_RULE_SINE:
        for ax in mounts:
            r = run_banding_condition(400, images, mu=10.0, kappa=4.0, band_axis=ax, **kw)
            name = f"{label}, mount {ax}"
            results[f"E4_rule_{kw['band_period']:.0f}_{kw['banding']}_{ax}"] = dict(r, _label=name)
            _print_rule_condition(name, r, ctrl[ax]["_err"]["raw"], images)


def experiment_e5(images, results):
    print("\nE5  Directional shadow (raking light from one side), offset (1.5, 0) px (mu 30, kappa 4)")
    for sh in (None, (1.5, 0.0)):
        r = run_condition(500, images, mu=30.0, kappa=4.0, shadow=sh)
        results[f"E5_shadow{'on' if sh else 'off'}"] = r
        report(f" shadow {'on' if sh else 'off'}", r)


def experiment_e6(images, results):
    print("\nE6  Strand aspect ratio (mu 0, kappa 4): end edges dilute the texture estimate")
    for length in (60.0, 120.0, 240.0):
        r = run_condition(600 + int(length), images, mu=0.0, kappa=4.0, length=length)
        results[f"E6_len{int(length)}"] = r
        report(f" length {length:.0f} px x width 24 px (aspect {length / 24:.1f})", r)


def experiment_e7(images, results):
    print("\nE7  Mat density (occlusion) at kappa 2, mu 0: crossing strands are cut into short visible pieces")
    for n in (120, 650, 1300):
        r = run_condition(700 + n, images, mu=0.0, kappa=2.0, n=n)
        results[f"E7_n{n}"] = r
        report(f" {n} strands per 768 x 768 px", r)


def experiment_e8(images, results):
    print("\nE8  Rotational bias, the same strands rotated in place (one seed: same positions, sizes and"
          " deviations from mu) (kappa 16, 3x images)")
    for mu in (0.0, 10.0, 22.5, 30.0, 45.0, 67.5, 80.0, 90.0):
        r = run_condition(800, 3 * images, mu=mu, kappa=16.0)
        results[f"E8_mu{mu}"] = r
        print(f"  mu {mu:5.1f}: truth mean {r['truth']['mean']:+6.2f} (n {r['truth']['n']})  errors: {mean_errors(r)}")


def experiment_e9(images, results):
    print("\nE9  Collinear merging of edge pieces vs mat density (mu 0)")
    for kappa in (2.0, 4.0):
        for n in (650, 1300):
            r = run_condition(900 + n + int(kappa), images, mu=0.0, kappa=kappa, n=n)
            results[f"E9_k{kappa}_n{n}"] = r
            report(f" kappa {kappa}, {n} strands", r)


def experiment_e10(images, results):
    print("\nE10 Expected flake width set wrong (true mean width 24 px, mu 0, kappa 4; same strands in every row)")
    for ws in (8.0, 12.0, 16.0, 20.0, 24.0, 30.0, 36.0, 48.0):
        r = run_condition(1000, images, width_set=ws, mu=0.0, kappa=4.0)
        results[f"E10_w{int(ws)}"] = r
        report(f" width set to {ws:.0f} px", r, methods=("A_tensor", "B_merged"))


def experiment_e11(images, results):
    print("\nE11 Flake width estimated from paired long edges (estimate_width_paired), aspect 5:1, ~same cover")
    for width in (12.0, 24.0, 36.0):
        n = int(round(650 * (24.0 * 120.0) / (width * 5.0 * width)))
        for kappa in (2.0, 4.0):
            rng = np.random.default_rng(1100 + int(width) + int(kappa))
            est, true_w, pairs = [], [], 0
            for _ in range(images):
                img, truth = render_mat(rng, n=n, mu=0.0, kappa=kappa, length=5.0 * width, width=width)
                w, k = estimate_width_paired(img)
                est.append(w)
                pairs += k
                true_w.append(truth["width"][truth["visible_frac"] >= 0.25])
            tw = float(np.mean(np.concatenate(true_w)))
            e = np.asarray(est)
            rel = 100.0 * (e / tw - 1.0)
            results[f"E11_w{int(width)}_k{kappa}"] = {"true_mean_width": tw, "estimates": e.tolist(),
                                                      "pairs": pairs}
            print(f"  width {width:4.0f} px, kappa {kappa}, {n} strands: true mean (visible) {tw:5.1f} px,"
                  f" estimates {', '.join(f'{x:5.1f}' for x in e)} px ({rel.mean():+5.1f} % mean,"
                  f" worst {rel[np.argmax(np.abs(rel))]:+5.1f} %), {pairs // images} pairs per image")


def _clip_lengths(cx, cy, ux, uy, length, w, h):
    """Length of each segment (centre, unit direction, length) inside [0, w] x [0, h] (Liang-Barsky)."""
    t0 = np.full(cx.shape, -length / 2.0)
    t1 = np.full(cx.shape, length / 2.0)
    for p, q in ((-ux, cx), (ux, w - cx), (-uy, cy), (uy, h - cy)):
        with np.errstate(divide="ignore", invalid="ignore"):
            r = q / p
        t0 = np.where(p < 0, np.maximum(t0, r), t0)
        t1 = np.where(p > 0, np.minimum(t1, r), t1)
        t1 = np.where((p == 0) & (q < 0), t0 - 1.0, t1)
    return np.maximum(0.0, t1 - t0)


def experiment_e12(images, results):
    print("\nE12 ROI border rule (geometry only, no images): which flake edges count when the ROI cuts them."
          "\n    truth = edges whose centre lies in the ROI; clip = clip to the ROI, then the minimum length"
          " (100 px);\n    inside = only edges entirely inside. Edge lengths 100-400 px, MD along the ROI's"
          " short side.")
    rng = np.random.default_rng(1200)
    n = 1_000_000
    for (w, h, kappa, mu) in ((2304, 1296, 4.0, 0.0), (2000, 666, 4.0, 0.0), (2000, 666, 2.0, 30.0),
                              (1296, 1296, 2.0, 30.0)):
        cx = rng.uniform(-400, w + 400, n)
        cy = rng.uniform(-400, h + 400, n)
        th = wrap_axial(sample_axial_vonmises(rng, mu, kappa, n))
        length = rng.uniform(100.0, 400.0, n)
        ux, uy = np.sin(np.radians(th)), np.cos(np.radians(th))   # theta measured from the y axis (MD)
        inside_c = (cx >= 0) & (cx <= w) & (cy >= 0) & (cy <= h)
        cl = _clip_lengths(cx, cy, ux, uy, length, w, h)
        rows = {}
        for name, sel in (("truth", inside_c), ("clip", cl >= 100.0), ("inside", inside_c & (cl >= length - 1e-9))):
            rows[name] = axial_stats(th[sel])
        t = rows["truth"]
        results[f"E12_{w}x{h}_k{kappa}_mu{mu}"] = rows
        print(f"  ROI {w} x {h} px, kappa {kappa}, mu {mu}: " + "  ".join(
            f"{k} mean {axial_diff(v['mean'], t['mean']):+5.2f} sd {v['sd'] - t['sd']:+5.2f}"
            f" in20 {v['in20'] - t['in20']:+5.1f}" for k, v in rows.items() if k != "truth"))


# ----------------------------------------------------------------------------------------------
# E13: light check, readout time and brightness drift at the row level (design 6.16)
# ----------------------------------------------------------------------------------------------

FL_ROWS = 2160          # sensor rows of the frame (readout direction)
FL_TAB = 4096           # samples per flicker period in the waveform tables
FL_EXPOSURE_S = 1.0 / 4200.0
FL_BURST = 27           # light check / readout burst: 27 frames at 1/27 s
FL_BINS = {4: 50, 6: 60, 8: 100, 12: 120}   # DFT bin of the 27-frame series -> flicker frequency (Hz)


def flicker_table(kind, F, depth=0.0, tau_s=0.0, duty=0.6):
    """One period of a flicker waveform of frequency F (Hz), FL_TAB samples, normalized to mean 1.

    kind: "sine" (1 + depth cos), "rect" (full-wave rectified sine: |sin| with period 1/F, i.e. F = 2 x mains),
    "halfsine" (half-wave rectified sine, F = mains), "square" (on for `duty` of the period, off = 0: an LED
    with an off-time). tau_s > 0 passes the waveform through a first-order low-pass (phosphor or smoothing
    capacitor) and returns its periodic steady state.
    """
    ph = (np.arange(FL_TAB) + 0.5) / FL_TAB
    if kind == "sine":
        w = 1.0 + depth * np.cos(2.0 * math.pi * ph)
    elif kind == "rect":
        w = np.abs(np.sin(math.pi * ph))
    elif kind == "halfsine":
        w = np.maximum(0.0, np.sin(2.0 * math.pi * ph))
    elif kind == "square":
        w = (ph < duty).astype(np.float64)
    else:
        raise ValueError(kind)
    if tau_s > 0:
        a = math.exp(-1.0 / (FL_TAB * F * tau_s))
        y = np.empty_like(w)
        acc = 0.0
        for i in range(FL_TAB):                     # zero-state response over one period
            acc = a * acc + (1.0 - a) * w[i]
            y[i] = acc
        y0 = y[-1] / (1.0 - a ** FL_TAB)            # periodic steady state: y(0) = a^N y(0) + y_zs(N)
        w = y + y0 * a ** (np.arange(FL_TAB) + 1.0)
    return w / w.mean()


def flicker_light(tab, F, t, exposure=FL_EXPOSURE_S):
    """Light integrated over [t, t + exposure] (s), relative to its mean, for the waveform table `tab`."""
    cum = np.concatenate([[0.0], np.cumsum(tab) / FL_TAB])

    def W(phase):
        fl = np.floor(phase)
        return fl + np.interp((phase - fl) * FL_TAB, np.arange(FL_TAB + 1), cum)
    a = F * np.asarray(t, dtype=np.float64)
    b = a + F * exposure
    return (W(b) - W(a)) / (b - a)


def flicker_shape(tab):
    """(peak-to-peak depth (max - min) / (max + min), fundamental amplitude / mean) of a waveform table."""
    fund = 2.0 * abs(np.fft.rfft(tab)[1]) / FL_TAB / tab.mean()
    return float((tab.max() - tab.min()) / (tab.max() + tab.min())), float(fund)


def fl_surface(rng, n_frames, drift_px=0.0, shake_px=0.0, tex=0.0, vign=0.3, corr_rows=15):
    """Row profile of the surface for each frame, shape (n_frames, FL_ROWS).

    A fixed vignetting / uneven light (1 - vign at the frame ends) times a texture of relative RMS `tex`
    (smoothed over `corr_rows` rows) that moves along the readout by drift_px per frame plus a random shake
    of shake_px (standard deviation) per frame. tex is the RMS of the row-mean profile itself, which is
    pessimistic for a real mat (a row mean averages hundreds of flakes).
    """
    y = np.arange(FL_ROWS, dtype=np.float64)
    c = (FL_ROWS - 1) / 2.0
    v = 1.0 - vign * ((y - c) / c) ** 2
    margin = int(abs(drift_px) * n_frames + 10.0 * shake_px + 64)
    n = FL_ROWS + 2 * margin
    t = np.ones(n)
    if tex > 0:
        z = np.convolve(rng.standard_normal(n + 2 * corr_rows), np.ones(corr_rows), mode="same")
        z = z[corr_rows:-corr_rows]
        t = 1.0 + tex * (z - z.mean()) / z.std()
    out = np.empty((n_frames, FL_ROWS))
    for k in range(n_frames):
        sh = margin + drift_px * k + (shake_px * rng.standard_normal() if shake_px > 0 else 0.0)
        out[k] = v * np.interp(y + sh, np.arange(n, dtype=np.float64), t)
    return out


def fl_frames(rng, tab, F, T_r, frame_s, surface, noise=5e-4, reverse=False, exposure=FL_EXPOSURE_S):
    """Row-mean profiles (n_frames, FL_ROWS) of frames whose row r starts its exposure at
    t0 + k frame_s + r T_r / FL_ROWS (reverse: rows read bottom to top), under flicker `tab` at F Hz."""
    y = np.arange(FL_ROWS, dtype=np.float64)
    rt = ((FL_ROWS - 1 - y) if reverse else y) * T_r / FL_ROWS
    t0 = rng.uniform(0.0, 1.0)
    n = surface.shape[0]
    out = np.empty((n, FL_ROWS))
    for k in range(n):
        out[k] = surface[k] * flicker_light(tab, F, t0 + k * frame_s + rt, exposure)
    if noise > 0:
        out *= 1.0 + noise * rng.standard_normal(out.shape)
    return out


def fl_strips(prof, roi, strip=32):
    """Strip means (n_frames, n_strips) over ROI rows [roi[0], roi[1]) cut into strips of <= `strip` rows,
    and the strip centre rows."""
    idx = np.array_split(np.arange(roi[0], roi[1]), int(math.ceil((roi[1] - roi[0]) / strip)))
    series = np.stack([prof[:, i].mean(axis=1) for i in idx], axis=1)
    centres = np.array([0.5 * (i[0] + i[-1]) for i in idx])
    return series, centres


def _detrend(series):
    n = series.shape[0]
    a = np.vstack([np.ones(n), np.arange(n, dtype=np.float64)]).T
    coef, *_ = np.linalg.lstsq(a, series, rcond=None)
    return series - a @ coef


def light_check(prof, roi, strip=32):
    """Design 6.16 light check on a 27-frame burst: per strip, linear trend removed, real DFT over the
    frames; flicker index = RMS over the strips of the one-sided amplitude in the strongest of bins 4, 6, 8,
    12, relative to the ROI mean; that bin gives the frequency; floor = median over the other bins 1-13."""
    series, _ = fl_strips(prof, roi, strip)
    n = series.shape[0]
    amp = 2.0 * np.abs(np.fft.rfft(_detrend(series), axis=0)) / n
    mean = float(series.mean())
    rms = np.sqrt(np.mean(amp ** 2, axis=1)) / mean
    best = max(FL_BINS, key=lambda b: rms[b])
    other = [b for b in range(1, n // 2 + 1) if b not in FL_BINS]
    return {"index": float(rms[best]), "hz": FL_BINS[best], "floor": float(np.median(rms[other])),
            "by_bin": {FL_BINS[b]: float(rms[b]) for b in FL_BINS}}


def readout_phase(prof, roi, F, frame_s, strip=32, window="hann"):
    """Readout time by the phase slope: per strip the DFT over the frames at the bin of the positive
    flicker frequency (F frame_s cycles per frame, aliased), phase unwrapped along the strips, straight line
    fitted against the strip centre rows with weights |X|^2. slope = 2 pi F T_r / rows per row; positive
    when the rows are read top to bottom. Returns (T_r in s, direction +1 / -1).

    window "detrend": the light check's series (linear trend removed, no window); "hann": mean removed and
    a Hann window over the frames, which keeps the flicker's own mirror image (3 bins away at 120 Hz) and
    a trend out of the bin when the mains frequency is off nominal.
    """
    series, centres = fl_strips(prof, roi, strip)
    n = series.shape[0]
    cyc = F * frame_s
    b = int(round((cyc - math.floor(cyc)) * n)) % n
    if window == "hann":
        s = (series - series.mean(axis=0)) * np.hanning(n + 2)[1:-1, None]
    else:
        s = _detrend(series)
    x = s.T @ np.exp(-2j * math.pi * b * np.arange(n) / n)
    ph = np.unwrap(np.angle(x))
    w = np.abs(x)
    a = np.vstack([centres, np.ones_like(centres)]).T * w[:, None]
    slope = float(np.linalg.lstsq(a, ph * w, rcond=None)[0][0])
    return abs(slope) * FL_ROWS / (2.0 * math.pi * F), (1 if slope > 0 else -1)


def readout_design(prof, F, grid_n=600, refine=60):
    """The current design's readout fit (6.16) on full-frame row profiles: ratio of consecutive frames,
    offset + fundamental + 2nd harmonic with a free period P, coarse search over 0.25-4 frame heights
    (geometric grid), refined per pair (golden section on the variable-projection residual, the same optimum
    as Gauss-Newton), median P over the pairs; T_r = rows / (F P). Denominators are held at >= 1 % of the
    frame mean so that dark rows (an LED's off-time) do not divide by zero."""
    rows = prof.shape[1]
    yy = np.arange(rows, dtype=np.float64)
    den = np.maximum(prof[:-1], 0.01 * prof[:-1].mean(axis=1, keepdims=True))
    r = (prof[1:] / den).T                          # rows x pairs
    rr = (r ** 2).sum(axis=0)

    def rss(p, cols=None):
        w1 = 2.0 * math.pi * yy / p
        q, _ = np.linalg.qr(np.vstack([np.ones(rows), np.cos(w1), np.sin(w1), np.cos(2 * w1),
                                       np.sin(2 * w1)]).T)
        rc = r if cols is None else r[:, cols]
        return (rr if cols is None else rr[cols]) - ((q.T @ rc) ** 2).sum(axis=0)
    grid = np.geomspace(0.25 * rows, 4.0 * rows, grid_n)
    vals = np.array([rss(p) for p in grid])         # grid x pairs
    g = (math.sqrt(5.0) - 1.0) / 2.0
    periods = []
    for j in range(r.shape[1]):
        i = int(np.argmin(vals[:, j]))
        a, b = grid[max(i - 1, 0)], grid[min(i + 1, grid_n - 1)]
        c1, c2 = b - g * (b - a), a + g * (b - a)
        f1, f2 = rss(c1, [j])[0], rss(c2, [j])[0]
        for _ in range(refine):
            if f1 < f2:
                b, c2, f2 = c2, c1, f1
                c1 = b - g * (b - a)
                f1 = rss(c1, [j])[0]
            else:
                a, c1, f1 = c1, c2, f2
                c2 = a + g * (b - a)
                f2 = rss(c2, [j])[0]
        periods.append(0.5 * (a + b))
    return rows / (F * float(np.median(periods)))


# Waveforms: (label, kind, depth, tau_s, duty, half_wave)
FL_WAVES = (
    ("steady light (no flicker)", "sine", 0.0, 0.0, 0.0, False),
    ("sine 0.5 %", "sine", 0.005, 0.0, 0.0, False),
    ("sine 2 %", "sine", 0.02, 0.0, 0.0, False),
    ("sine 10 %", "sine", 0.10, 0.0, 0.0, False),
    ("sine 30 %", "sine", 0.30, 0.0, 0.0, False),
    ("rectified sine", "rect", 0.0, 0.0, 0.0, False),
    ("rectified, phosphor 2 ms", "rect", 0.0, 0.002, 0.0, False),
    ("rectified, capacitor 10 ms", "rect", 0.0, 0.010, 0.0, False),
    ("LED off-time, duty 0.6", "square", 0.0, 0.0, 0.6, False),
    ("half-wave rectified sine", "halfsine", 0.0, 0.0, 0.0, True),
    ("half-wave LED, duty 0.6", "square", 0.0, 0.0, 0.6, True),
)
# Surfaces: (label, drift px/frame, shake px, texture RMS)
FL_SURFACES = (
    ("still, vignetting + 1 % texture", 0.0, 0.0, 0.01),
    ("5 % texture, 1 px shake", 0.0, 1.0, 0.05),
    ("5 % texture, 3 px shake", 0.0, 3.0, 0.05),
    ("moving mat, 5 % texture, 150 px/frame", 150.0, 0.0, 0.05),
)
FL_TR_MS = (5.0, 8.0, 10.0, 12.0, 16.0, 20.0, 25.0)
FL_ROI = (330, 1830)                                # 1,500 rows, centred


def experiment_e13(images, results):
    print("\nE13 Light check, readout time and brightness drift, row-level simulation of design 6.16"
          f"\n    {FL_ROWS} rows, exposure 1/4,200 s, row noise 0.05 %, ROI rows {FL_ROI[0]}-{FL_ROI[1]}"
          " (1,500 rows), strips of <= 32 rows. Full-wave flicker F = 2 x mains, half-wave F = mains.")
    reps = 2 if images <= 2 else 4                   # per T_r and mains frequency; odd reps read bottom to top
    res = {}
    print("\n  E13a Light check (27 frames at 1/27 s) and readout time by the phase slope, T_r 5-25 ms, mains"
          f" 50 and 60 Hz, {reps} bursts each (half read bottom to top).\n  expected index = fundamental"
          " amplitude / mean of the waveform. T_r error = estimate / truth - 1 by the phase slope with a Hann"
          " window\n  over the frames and with the light check's detrended series. dir = readout direction right"
          " (Hann).")
    rng = np.random.default_rng(1300)
    for wl, kind, depth, tau, duty, half in FL_WAVES:
        for sl, drift, shake, tex in FL_SURFACES:
            idx, rel, hz_ok, floor, whole, errs, errs_dt, dir_ok, n = [], [], 0, [], [], [], [], 0, 0
            for f in (50, 60):
                F = float(f if half else 2 * f)
                tab = flicker_table(kind, F, depth, tau, duty)
                fund_f = max(flicker_shape(tab)[1], 1e-12)
                for tr in FL_TR_MS:
                    for rep in range(reps):
                        surf = fl_surface(rng, FL_BURST, drift, shake, tex)
                        prof = fl_frames(rng, tab, F, tr / 1000.0, 1.0 / FL_BURST, surf, reverse=bool(rep % 2))
                        lc = light_check(prof, FL_ROI)
                        idx.append(lc["index"])
                        rel.append(lc["index"] / fund_f - 1.0)
                        hz_ok += int(lc["hz"] == int(F))
                        floor.append(lc["floor"])
                        whole.append(light_check(prof, FL_ROI, strip=FL_ROI[1] - FL_ROI[0])["index"])
                        t_est, d = readout_phase(prof, FL_ROI, F, 1.0 / FL_BURST)
                        errs.append(100.0 * (t_est / (tr / 1000.0) - 1.0))
                        dir_ok += int(d == (-1 if rep % 2 else 1))
                        t_dt, _ = readout_phase(prof, FL_ROI, F, 1.0 / FL_BURST, window="detrend")
                        errs_dt.append(100.0 * (t_dt / (tr / 1000.0) - 1.0))
                        n += 1
            dep, fund = flicker_shape(flicker_table(kind, 50.0 if half else 100.0, depth, tau, duty))
            if depth == 0.0 and kind == "sine":         # steady light: only the index (false-alarm level) counts
                res[f"E13a_{wl}_{sl}"] = {"index": idx, "floor": floor, "n": n}
                print(f"  {wl:<27} | {sl:<37} | index {np.median(idx):.4f} [{min(idx):.4f}, {max(idx):.4f}]"
                      f" floor {np.median(floor):.4f}  (no flicker: index = noise level)")
                continue
            e, e_dt = np.asarray(errs), np.asarray(errs_dt)
            key = f"E13a_{wl}_{sl}"
            res[key] = {"depth": dep, "fundamental": fund, "index": idx, "index_rel_err": rel,
                        "freq_ok": hz_ok, "n": n,
                        "floor": floor, "whole_roi_index": whole, "tr_err_pct": errs, "tr_err_pct_detrend": errs_dt,
                        "dir_ok": dir_ok}
            print(f"  {wl:<27} | {sl:<37} | depth {dep:4.2f} exp {fund:.4f} | index {np.median(idx):.4f}"
                  f" [{min(idx):.4f}, {max(idx):.4f}] /exp-1 [{100 * min(rel):+5.1f}, {100 * max(rel):+5.1f}] %"
                  f" floor {np.median(floor):.4f} whole-ROI {np.median(whole):.4f}"
                  f" | F ok {hz_ok}/{n} | T_r err % Hann [{e.min():+6.2f}, {e.max():+6.2f}] detrend"
                  f" [{e_dt.min():+6.2f}, {e_dt.max():+6.2f}] | dir {dir_ok}/{n}")

    print("\n  E13b Whole-ROI mean instead of strips (sine 30 %, still): index for ROIs of 1,000 and 1,500 rows")
    for roi_h in (1000, 1500):
        roi = ((FL_ROWS - roi_h) // 2, (FL_ROWS - roi_h) // 2 + roi_h)
        for f in (50, 60):
            for tr in (8.0, 12.0, 16.0):
                tab = flicker_table("sine", 2.0 * f, 0.3)
                surf = fl_surface(rng, FL_BURST, 0.0, 0.0, 0.01)
                prof = fl_frames(rng, tab, 2.0 * f, tr / 1000.0, 1.0 / FL_BURST, surf)
                s32 = light_check(prof, roi)["index"]
                wh = light_check(prof, roi, strip=roi_h)["index"]
                band = FL_ROWS / (2.0 * f * tr / 1000.0)
                res[f"E13b_{roi_h}_{f}_{tr}"] = {"strips": s32, "whole": wh}
                print(f"  ROI {roi_h} rows, mains {f} Hz, T_r {tr:4.1f} ms (band period {band:5.0f} rows):"
                      f" strips {s32:.4f}  whole ROI {wh:.4f}")

    print("\n  E13c Off-nominal mains (LED off-time, duty 0.6, still): the burst no longer holds whole flicker"
          " periods")
    for f in (49.9, 50.1, 59.9, 60.1):
        tab = flicker_table("square", 2.0 * f, duty=0.6)
        out = []
        for tr in (5.0, 16.0, 25.0):
            surf = fl_surface(rng, FL_BURST, 0.0, 0.0, 0.01)
            prof = fl_frames(rng, tab, 2.0 * f, tr / 1000.0, 1.0 / FL_BURST, surf)
            lc = light_check(prof, FL_ROI)
            t_h, _ = readout_phase(prof, FL_ROI, 2.0 * round(f), 1.0 / FL_BURST)   # the app assumes nominal F
            t_d, _ = readout_phase(prof, FL_ROI, 2.0 * round(f), 1.0 / FL_BURST, window="detrend")
            out.append((lc["index"], lc["hz"], 100.0 * (t_h / (tr / 1000.0) - 1.0),
                        100.0 * (t_d / (tr / 1000.0) - 1.0)))
        res[f"E13c_{f}"] = out
        print(f"  mains {f} Hz: " + "  ".join(f"T_r {tr:.0f} ms: index {o[0]:.4f} {o[1]} Hz, T_r err Hann"
                                           f" {o[2]:+.2f} % detrend {o[3]:+.2f} %"
                                           for tr, o in zip((5.0, 16.0, 25.0), out)))

    print("\n  E13d Current design's fit (ratio of consecutive frames, free period, median over 26 pairs) vs the"
          " phase slope,\n  same bursts, full frame for the fit and the ROI for the phase slope; T_r 5, 8, 16,"
          " 25 ms, 50 and 60 Hz")
    for wl, kind, depth, tau, duty, half in FL_WAVES[1:6] + FL_WAVES[8:9]:
        for sl, drift, shake, tex in FL_SURFACES[:2]:
            ed, ep = [], []
            for f in (50, 60):
                F = 2.0 * f
                tab = flicker_table(kind, F, depth, tau, duty)
                for tr in (5.0, 8.0, 16.0, 25.0):
                    surf = fl_surface(rng, FL_BURST, drift, shake, tex)
                    prof = fl_frames(rng, tab, F, tr / 1000.0, 1.0 / FL_BURST, surf)
                    ed.append(100.0 * (readout_design(prof, F) / (tr / 1000.0) - 1.0))
                    ep.append(100.0 * (readout_phase(prof, FL_ROI, F, 1.0 / FL_BURST)[0] / (tr / 1000.0) - 1.0))
            ed, ep = np.asarray(ed), np.asarray(ep)
            res[f"E13d_{wl}_{sl}"] = {"design": ed.tolist(), "phase": ep.tolist()}
            print(f"  {wl:<27} | {sl:<33} | design fit T_r err % [{ed.min():+7.2f}, {ed.max():+7.2f}]"
                  f" (> 3 %: {int((np.abs(ed) > 3).sum())}/{ed.size}) | phase slope [{ep.min():+6.2f}, {ep.max():+6.2f}]")

    print("\n  E13f Readout test exposure and mains offset (phase slope with Hann window, T_r 5-25 ms, 50 and 60 Hz,"
          " 2 bursts each):\n  sharp light edges alias the 8th/10th (60/120 Hz) or 26th/28th (50/100 Hz) harmonic"
          " onto the flicker bin; an exposure of 1/(2F) removes\n  every even harmonic. max |T_r error| %, nominal"
          " mains | mains 0.1 Hz above and below nominal")
    for wl, kind, depth, tau, duty, half in FL_WAVES[1:]:
        for sl, drift, shake, tex in FL_SURFACES[:2]:
            line = []
            for ex_lab in ("1/4200", "1/1000", "1/(2F)"):
                e_nom, e_off = [], []
                for f0 in (50, 60):
                    Fn = float(f0 if half else 2 * f0)
                    ex = 1.0 / (2.0 * Fn) if ex_lab == "1/(2F)" else 1.0 / float(ex_lab[2:])
                    for df in (0.0, 0.1, -0.1):
                        F = Fn * (f0 + df) / f0
                        tab = flicker_table(kind, F, depth, tau, duty)
                        for tr in FL_TR_MS:
                            for rep in range(2):
                                surf = fl_surface(rng, FL_BURST, drift, shake, tex)
                                prof = fl_frames(rng, tab, F, tr / 1000.0, 1.0 / FL_BURST, surf, exposure=ex,
                                                 reverse=bool(rep % 2))
                                err = 100.0 * (readout_phase(prof, FL_ROI, Fn, 1.0 / FL_BURST)[0] / (tr / 1000.0) - 1.0)
                                (e_nom if df == 0.0 else e_off).append(err)
                res[f"E13f_{wl}_{sl}_{ex_lab}"] = {"nominal": e_nom, "off": e_off}
                line.append(f"{ex_lab:>6} s: {np.max(np.abs(e_nom)):5.2f} | {np.max(np.abs(e_off)):5.2f}")
            print(f"  {wl:<27} | {sl:<33} | " + "   ".join(line))

    print("\n  E13e Brightness drift at the run's 1/30 s frames over 60 s (1,800 frames), reference = mean of the"
          " first second.\n  max |ROI mean rel - 1| vs max over frames of the RMS over strips of |strip mean rel - 1|")
    cases = [("sine 30 %, mains 60.02 Hz", "sine", 0.30, 60.02, 0.0, 0.0),
             ("sine 10 %, mains 60.02 Hz", "sine", 0.10, 60.02, 0.0, 0.0),
             ("sine 30 %, mains 50.02 Hz", "sine", 0.30, 50.02, 0.0, 0.0),
             ("steady light, moving 5 % texture", "sine", 0.0, 60.0, 150.0, 0.05),
             ("steady light, moving 2 % texture", "sine", 0.0, 60.0, 150.0, 0.02)]
    n_frames = 1800
    for cl, kind, depth, f, drift, tex in cases:
        for roi_h in (500, 1500):
            roi = ((FL_ROWS - roi_h) // 2, (FL_ROWS - roi_h) // 2 + roi_h)
            for tr in (8.0, 12.0, 16.0):
                tab = flicker_table(kind, 2.0 * f, depth)
                surf = fl_surface(rng, n_frames, drift, 0.0, tex, vign=0.3)
                prof = fl_frames(rng, tab, 2.0 * f, tr / 1000.0, 1.0 / 30.0, surf)
                series, _ = fl_strips(prof, roi)
                roi_mean = prof[:, roi[0]:roi[1]].mean(axis=1)
                rel_roi = roi_mean / roi_mean[:30].mean() - 1.0
                rel_s = series / series[:30].mean(axis=0) - 1.0
                rms_s = np.sqrt(np.mean(rel_s ** 2, axis=1))
                res[f"E13e_{cl}_{roi_h}_{tr}"] = {"roi": float(np.abs(rel_roi).max()), "strips": float(rms_s.max()),
                                                 "strips_p99": float(np.percentile(rms_s, 99))}
                print(f"  {cl:<33} ROI {roi_h:4d} rows, T_r {tr:4.1f} ms: ROI mean {100 * np.abs(rel_roi).max():5.2f} %"
                      f"  strips RMS {100 * rms_s.max():5.2f} % (99th pct {100 * np.percentile(rms_s, 99):5.2f} %)")
    results["E13"] = res

if __name__ == "__main__":
    sys.exit(main())
