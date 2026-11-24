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

Results of record (see README.md), 8 images per condition, about 28 minutes:
  python3 -I tools/lab/flake_lab.py --images 8 --json tools/lab/results-<date>.json \
      | tee tools/lab/results-<date>.txt

Requires numpy and opencv-python-headless (see requirements.txt).
"""

from __future__ import annotations

import argparse
import json
import math
import os
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
               banding_shape="sine", band_duty=0.5, band_ramp=64.0, band_off=0.0, noise_blur=0.0, clean=None,
               noise_field=None):
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
    noise: standard deviation of the added Gaussian noise (lab units, 1 = full scale). noise_blur > 0 filters
        the noise field with a Gaussian of that sigma (px) and rescales it to the same standard deviation, as an
        ISP's denoising leaves it; it draws the same random numbers, so the mats stay the same.
    clean: optional list; the noiseless float image (after optics, blur and banding) is appended to it.
    noise_field: optional list; the standard normal field behind the noise is appended to it, so that the caller
        can make the same mat at other noise levels with add_noise (bit-identical to rendering it again with that
        noise; the generator draws the same numbers either way).
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
    if clean is not None:
        clean.append(img.copy())
    if noise_field is not None:
        z = rng.normal(0.0, 1.0, img.shape)
        noise_field.append(z)
        img8 = add_noise(img, z, noise, noise_blur)
    else:
        if noise_blur > 0:
            field = cv2.GaussianBlur(rng.normal(0.0, 1.0, img.shape).astype(np.float32), (0, 0), noise_blur)
            img = img + field * np.float32(noise / max(float(field.std()), 1e-12))
        else:
            img = img + rng.normal(0.0, noise, img.shape).astype(np.float32)
        img8 = np.clip(np.round(img * 255.0), 0, 255).astype(np.uint8)

    ids, counts = np.unique(label[label >= 0], return_counts=True)
    vis = np.zeros(n)
    vis[ids] = counts
    frac = vis / (lengths * widths)
    truth = {"theta": thetas, "visible_frac": frac, "length": lengths, "width": widths}
    return img8, truth


def add_noise(img, z, noise, noise_blur=0.0):
    """8-bit image of the noiseless float image img plus Gaussian noise of standard deviation `noise` made from the
    standard normal field z (render_mat's noise_field), exactly as render_mat adds it: white, or with noise_blur > 0
    filtered with a Gaussian of that sigma (px) and rescaled to the same standard deviation."""
    if noise_blur > 0:
        field = cv2.GaussianBlur(z.astype(np.float32), (0, 0), noise_blur)
        out = img + field * np.float32(noise / max(float(field.std()), 1e-12))
    else:
        out = img + (noise * z).astype(np.float32)
    return np.clip(np.round(out * 255.0), 0, 255).astype(np.uint8)


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


BAND_STRIPS = 6   # strips along the sensor rows for band_common


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
                   (Gaussian derivative, sigma 1 px, as the tensor's); its texture part grows as 1 / ROI width
      band_common  the part of grad_frac common to the ROI's strips along the rows (review cycle 4): mean
                   product of the strips' row-profile slopes over pairs of strips that are not neighbours, over
                   the same denominator; ~0 without bands at any ROI width or strand direction
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
    den = max(float(np.mean(dimg.astype(np.float64) ** 2)), 1e-12)
    out["grad_frac"] = float(np.mean(drow ** 2) / den)
    # band_common: the same row-to-row difference per strip of the ROI cut along the sensor rows into
    # BAND_STRIPS equal strips, multiplied pairwise over strips that are not neighbours (the gap of at least one
    # strip keeps most single strands out of both) and averaged, over the same denominator. Bands are a gain of
    # the sensor row, common to every strip, so their slope adds to every product; the strands' own row
    # structure differs from strip to strip and averages towards zero, so the value does not grow as the ROI
    # narrows or as the strands turn towards the rows (grad_frac does: its texture part scales with 1 / ROI
    # width). It can come out slightly negative without bands.
    a = img if band_axis == "y" else img.T          # sensor rows as rows of a
    parts = np.array_split(np.arange(a.shape[1]), BAND_STRIPS)
    ds = [np.diff(np.convolve(a[:, c].mean(axis=1), np.ones(8) / 8.0, mode="valid")) for c in parts]
    out["band_common"] = float(np.mean([np.mean(ds[i] * ds[j]) for i in range(BAND_STRIPS)
                                        for j in range(i + 2, BAND_STRIPS)])) / den

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
BAND_DARK_MIN = 0.15     # exclude a shot (both methods) whose row_min is below this (near-dark rows)
BAND_GRAD_MIN = 0.03     # cycle-3 flag on grad_frac; printed for comparison only (it grows as the ROI narrows)
BAND_COMMON_MIN = 0.01   # banding that matters when band_common >= this
BAND_R_MIN = 0.76        # A_tensor is corrected row by row only when the median R of A_tensor on the row-corrected
                         # copy is >= this (kappa 4 layers read 0.79-0.85, kappa 3 0.76-0.78, kappa 2.5 0.73-0.75) ...
BAND_PSI_ROWS = 45.0     # ... and the median angle (deg) between the strands and the sensor rows is >= this (review
                         # cycle 5, E4 regime boundary: dividing row by row costs up to -0.46 deg on the mean at psi
                         # 30-40 and -0.34 at psi 45 with kappa 2.5; 0.76 keeps that layer out of rows on a median
                         # of 5 shots)
BAND_SMOOTH_FLAKE = 0.7  # otherwise A_tensor's row means are smoothed over this many flake widths ...
BAND_SMOOTH_MAX = 25     # ... but over at most this many rows (band periods do not scale with the strands) ...
BAND_SMOOTH_ROW_MIN = 0.5  # ... and A_tensor is excluded when row_min is below this (smoothing cannot follow deep
                           # band edges)


def strand_direction(stats, band_axis):
    """(psi, R) of an A_tensor result: psi = angle (deg, 0-90) between its mean direction and the sensor rows
    (rows run along x, lab angle 0, when band_axis is "y"; along y, 90 deg, when it is "x"), R = its mean
    resultant length (doubled angles, as axial_stats). The rule uses the result on the row-corrected copy
    (line_normalize8): bands pull the raw tensor towards the rows and lower its R."""
    if not stats.get("n", 0):
        return 0.0, 0.0
    return abs(axial_diff(stats["mean"], 0.0 if band_axis == "y" else 90.0)), stats["R"]


def band_window(wset):
    """Rows over which the row means are smoothed for the correction when the strands run along the rows: 0.7
    flake widths (odd), at most BAND_SMOOTH_MAX."""
    return min(int(round(BAND_SMOOTH_FLAKE * wset)) | 1, BAND_SMOOTH_MAX)


def direction_regime(psi, r_dir):
    """A_tensor's correction regime from the strands' direction: "rows" (strands across or oblique to the rows:
    divide every row by its mean) or "along" (along the rows, or a weakly aligned or random layer: smooth)."""
    return "rows" if r_dir >= BAND_R_MIN and psi >= BAND_PSI_ROWS else "along"


def _regime_rule_text():
    """direction_regime in words, for the headers."""
    return f"rows when median psi >= {BAND_PSI_ROWS:.0f} and median R >= {BAND_R_MIN}, otherwise along"


def condition_regime(dirs, mets, dark_min=BAND_DARK_MIN):
    """The regime of a condition (review cycle 4: decided per condition, not per shot): direction_regime of the
    median psi and the median R over its shots that are not dark. This stands for the app's rolling median over
    a run's recent shots (the layer is stationary within a run); a per-shot decision would let A's exclusions
    select shots by alignment. Returns (regime, median psi, median R)."""
    use = [d for d, m in zip(dirs, mets) if m["row_min"] >= dark_min] or list(dirs)
    psi = float(np.median([d[0] for d in use]))
    r_dir = float(np.median([d[1] for d in use]))
    return direction_regime(psi, r_dir), psi, r_dir


def banding_rule(met, regime, wset, dark_min=BAND_DARK_MIN, common_min=BAND_COMMON_MIN):
    """Banding rule for one shot (review cycle 4). met: banding_metrics of the raw shot; regime: the condition's
    (condition_regime); wset: flake width setting (px). Returns (A_tensor correction, B_merged kept, state): the
    correction is None (excluded), "none", "rows" (every row divided by its mean) or an int W (row means smoothed
    over W rows); state is "dark", "clean" or "flagged". B_merged is excluded on every flagged shot: its error
    under bands depends on the strands' direction and width, and its paired noise cannot resolve a per-shot
    choice."""
    if met["row_min"] < dark_min:
        return None, False, "dark"
    if met["band_common"] < common_min:
        return "none", True, "clean"
    if regime == "rows":
        return "rows", False, "flagged"
    return (band_window(wset) if met["row_min"] >= BAND_SMOOTH_ROW_MIN else None), False, "flagged"


def run_banding_condition(seed, images, dark_min=BAND_DARK_MIN, common_min=BAND_COMMON_MIN, methods=BANDING_METHODS,
                          forced=False, **mat):
    """E4-style condition evaluated several ways on the same images, A_tensor and B_merged only (estimator
    settings of run_condition, so "raw" equals run_condition's result for the same seed and mat):
      raw   as rendered
      line  every sensor row divided by its mean (line_normalize8), on every image
      rule  banding_rule per shot: row_min < dark_min excludes both methods; band_common < common_min keeps both
            raw; otherwise B_merged is excluded and A_tensor is corrected by the condition's regime
            (condition_regime: median psi and R of A_tensor on the "line" copy): "rows" divides every row by its
            mean, "along" divides by the row means smoothed over band_window rows (A excluded when row_min <
            BAND_SMOOTH_ROW_MIN)
    methods: the methods evaluated; ("A_tensor",) skips B_merged, whose rule result does not depend on the regime.
    forced=True adds three variants: "smooth" (every image divided by its row means smoothed over band_window
    rows) and "rule_rows" / "rule_along" (banding_rule with the regime forced to rows / along: the app decides the
    regime once per run from its first flagged shots, so a layer near the boundary may get either).
    Returns {variant: {method: pooled stats with "se"}, "truth": ..., "_probe": [banding_metrics per image],
    "_dir": [(psi, R) per image], "_regime": {"regime", "psi", "R"} (the condition's), "_err": {variant: {method:
    [(mean err, sd err, in20 err) per image, None for an excluded shot]}}, "_rule": {"excluded": shots excluded
    for dark rows, "flagged": shots with band_common >= common_min, "flagged_grad": shots with grad_frac >=
    BAND_GRAD_MIN (the cycle-3 flag, for comparison), "shot_rows" / "shot_along": flagged shots per regime had
    it been decided per shot (the earlier rule, for comparison)}}.
    """
    rng = np.random.default_rng(seed)
    wset = float(mat.get("width", 24.0))
    axis = mat.get("band_axis", "y")
    win = band_window(wset)
    rules = (("rule", None),) + ((("rule_rows", "rows"), ("rule_along", "along")) if forced else ())
    variants = ("raw", "line") + (("smooth",) if forced else ()) + tuple(v for v, _ in rules)
    shots = []
    for _ in range(images):
        img, truth = render_mat(rng, **mat)
        est = {}
        copies = [("raw", img), ("line", line_normalize8(img, axis))]
        if forced:
            copies.append(("smooth", line_normalize8(img, axis, window=win)))
        for v, im in copies:
            est[v] = {"A_tensor": estimate_tensor(im, sigma_i=0.25 * wset)}
            if "B_merged" in methods:
                est[v]["B_merged"] = (estimate_segments_merged(im, min_len=1.5 * wset, max_gap=2.0 * wset)[0], None)
        shots.append({"img": img, "met": banding_metrics(img, axis), "est": est,
                      "tth": truth["theta"][truth["visible_frac"] >= 0.25],
                      "dir": strand_direction(axial_stats(*est["line"]["A_tensor"]), axis)})
    probes = [s["met"] for s in shots]
    dirs = [s["dir"] for s in shots]
    regime, med_psi, med_r = condition_regime(dirs, probes, dark_min)
    pools = {v: {m: [] for m in methods} for v in variants}
    errs = {v: {m: [] for m in methods} for v in variants}
    rule_truth = {v: {m: [] for m in methods} for v, _ in rules}
    counts = {"excluded": 0, "flagged": 0, "flagged_grad": 0, "shot_rows": 0, "shot_along": 0}
    for s in shots:
        met, est, tth = s["met"], s["est"], s["tth"]
        ts = axial_stats(tth)
        for v, forced_regime in rules:
            corr, keep_b, state = banding_rule(met, forced_regime or regime, wset, dark_min, common_min)
            if v == "rule":
                counts["flagged_grad"] += int(met["grad_frac"] >= BAND_GRAD_MIN)
                if state == "dark":
                    counts["excluded"] += 1
                elif state == "flagged":
                    counts["flagged"] += 1
                    counts["shot_" + direction_regime(*s["dir"])] += 1
            if corr is None:
                a_est = None
            elif corr == "none":
                a_est = est["raw"]["A_tensor"]
            elif corr == "rows":
                a_est = est["line"]["A_tensor"]
            else:
                if "smooth" not in est:
                    est["smooth"] = {"A_tensor": estimate_tensor(line_normalize8(s["img"], axis, window=corr),
                                                                 sigma_i=0.25 * wset)}
                a_est = est["smooth"]["A_tensor"]
            est[v] = {"A_tensor": a_est}
            if "B_merged" in methods:
                est[v]["B_merged"] = est["raw"]["B_merged"] if keep_b else None
            for m in methods:
                if est[v][m] is not None:
                    rule_truth[v][m].append(tth)
        for v in variants:
            for m in methods:
                if est[v][m] is None:
                    errs[v][m].append(None)
                    continue
                th, w = est[v][m]
                pools[v][m].append((th, np.ones_like(th) if w is None else w))
                ms = axial_stats(th, w)
                errs[v][m].append((axial_diff(ms["mean"], ts["mean"]), ms["sd"] - ts["sd"], ms["in20"] - ts["in20"])
                                  if ms.get("n", 0) and ts.get("n", 0) else None)
    out = {"truth": axial_stats(np.concatenate([s["tth"] for s in shots])), "_probe": probes, "_dir": dirs,
           "_regime": {"regime": regime, "psi": med_psi, "R": med_r}, "_rule": counts,
           "_err": {v: {m: [None if e is None else list(e) for e in errs[v][m]] for m in methods}
                    for v in variants}}
    for v in variants:
        out[v] = {}
        for m in methods:
            if v in rule_truth:
                tr = axial_stats(np.concatenate(rule_truth[v][m])) if rule_truth[v][m] else {"n": 0}
            else:
                tr = out["truth"]
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


def _banding_job(args):
    """Worker for _map_banding: (seed, images, render arguments) -> run_banding_condition result."""
    seed, images, kw = args
    return run_banding_condition(seed, images, **kw)


def _map_banding(jobs):
    """run_banding_condition over a list of (seed, images, render arguments) on up to 4 processes. Each
    condition seeds its own generator, so the results do not depend on the process count; order is kept."""
    procs = min(4, os.cpu_count() or 1, len(jobs))
    if procs <= 1:
        return [_banding_job(j) for j in jobs]
    import multiprocessing
    with multiprocessing.get_context("fork").Pool(procs) as pool:
        return pool.map(_banding_job, jobs, chunksize=1)


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
                    help="run only these experiments (E1..E14); repeatable")
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
                   ("E12", experiment_e12), ("E13", experiment_e13), ("E14", experiment_e14))
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


def _paired_text(errs, ctrl, in20=False):
    """Mean +- SE over images of (condition error - control error) for the mean and the spread (deg), and with
    in20 also for the share within 20 deg (points)."""
    out = []
    for j, lab in ((0, "mean"), (1, "sd")) + (((2, "in20"),) if in20 else ()):
        d = np.asarray([e[j] - c[j] for e, c in zip(errs, ctrl) if e is not None and c is not None])
        f = ".1f" if j == 2 else ".2f"
        if d.size == 0:
            out.append(f"{lab}   excluded")
        elif d.size == 1:
            out.append(f"{lab} {d[0]:+6{f}}")
        else:
            out.append(f"{lab} {d.mean():+6{f}}±{d.std(ddof=1) / math.sqrt(d.size):{f}}")
    return " ".join(out)


def _detect_text(probes, keys=("score", "score_long", "score_harm", "grad_frac", "band_common", "row_min",
                                "col_min")):
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
        extra = ""
        if v == "rule":
            c = r["_rule"]
            extra = (f" (dark rows: excluded {c['excluded']}/{images}; band_common flagged {c['flagged']}, regime"
                     f" {_regime_text(r)}; grad_frac would flag {c['flagged_grad']})")
        print(f"    {v:<4}" + "  ".join(f"  {m} {_paired_text(r['_err'][v][m], ctrl_raw_err[m], in20=True)}"
                                      for m in BANDING_METHODS) + extra)
    print(_detect_text(r["_probe"], keys=("score_harm", "grad_frac", "band_common", "row_min"))
          + "  " + _dir_text(r["_dir"]))


def _regime_text(r):
    """The condition's regime with its median psi and R, and the flagged shots' regimes had they been decided
    per shot (rows/along)."""
    g, c = r["_regime"], r["_rule"]
    return (f"{g['regime']} (median psi {g['psi']:.1f}, R {g['R']:.3f}; per shot {c['shot_rows']}/"
            f"{c['shot_along']})")


def _dir_text(dirs):
    """Median [min, max] of the strands' angle to the sensor rows (psi) and of R over the images."""
    psi, rr = [d[0] for d in dirs], [d[1] for d in dirs]
    return (f"psi {np.median(psi):.1f} [{min(psi):.1f}, {max(psi):.1f}]  R {np.median(rr):.3f}"
            f" [{min(rr):.3f}, {max(rr):.3f}]")


def _paired_means(errs, ctrl):
    """Mean over images of (condition error - control error): (mean, sd, in20), or None when all excluded."""
    d = np.asarray([[a - b for a, b in zip(e, c)] for e, c in zip(errs, ctrl) if e is not None and c is not None])
    return None if d.size == 0 else d.mean(axis=0)


def _rule_ok(r, ctrl_raw_err, random_layer=False, lim=(0.25, 0.5, 2.0), variant="rule"):
    """Criterion of review cycle 4 for the rule: every method within lim (mean deg, spread deg, in20 points) of
    the control, or excluded. A random layer has no mean direction, so only its spread and in20 count. variant:
    "rule", or with forced=True "rule_rows" / "rule_along"; the methods are those the condition evaluated."""
    for m in r["_err"][variant]:
        p = _paired_means(r["_err"][variant][m], ctrl_raw_err[m])
        if p is None:
            continue
        if (not random_layer and abs(p[0]) > lim[0]) or abs(p[1]) > lim[1] or abs(p[2]) > lim[2]:
            return False
    return True


def _compact_rule_line(name, r, ctrl_raw_err, images, random_layer=False):
    """One condition on one line: raw and rule changes (mean sd in20) per method, counts and the verdict."""
    def txt(v, m):
        p = _paired_means(r["_err"][v][m], ctrl_raw_err[m])
        n = sum(e is not None for e in r["_err"][v][m])
        return "      excluded      " if p is None else f"{p[0]:+5.2f} {p[1]:+5.2f} {p[2]:+5.1f} ({n})"
    c = r["_rule"]
    bc = [p["band_common"] for p in r["_probe"]]
    g = r["_regime"]
    return (f"  {name:<24} raw A {txt('raw', 'A_tensor')} B {txt('raw', 'B_merged')} | rule A"
            f" {txt('rule', 'A_tensor')} B {txt('rule', 'B_merged')} | dark {c['excluded']} flag {c['flagged']}"
            f" {g['regime']:<5} ({c['shot_rows']}/{c['shot_along']}) psi {g['psi']:4.1f} R {g['R']:.3f}"
            f" bc {np.median(bc):.3f} [{min(bc):.3f}] | {'ok' if _rule_ok(r, ctrl_raw_err, random_layer) else 'FAIL'}")


def experiment_e4_pwm(images, results):
    print("\nE4  (cont.) Deep PWM bands: a light on for `duty` of each period (off level 0 unless given), each row"
          " integrating it over\n    the exposure = `ramp` rows (64 rows ~ 1/4,200 s at an 8 ms readout of"
          " 2,160 rows; 128 rows ~ 16 ms), gain normalized to mean 1.\n    Same mats as above (mu 10, kappa"
          " 4). x = rows across MD (default mount), y = rows along MD. Changes from the control, mean ± SE over"
          "\n    the images of the paired difference (deg; in20 in points): raw; line = every sensor row divided by"
          f" its mean; rule (run_banding_condition):\n    shots with row_min < {BAND_DARK_MIN} excluded; when"
          f" band_common >= {BAND_COMMON_MIN}, B_merged is excluded and A_tensor is corrected by the\n    condition's"
          " regime, from the median over its shots of the angle psi of A_tensor on the row-corrected copy to the"
          f" sensor rows and of its R:\n    rows (median psi >= {BAND_PSI_ROWS:.0f} and median R >= {BAND_R_MIN}):"
          f" every row divided by its mean; along (otherwise): divided by the row means smoothed over\n    "
          f"{BAND_SMOOTH_FLAKE} flake widths (at most {BAND_SMOOTH_MAX} rows; A excluded when row_min <"
          f" {BAND_SMOOTH_ROW_MIN}). Per shot = flagged shots' regimes had they been decided per shot (rows/along)."
          "\n    Harmful: |mean| > 0.25, |sd| > 0.5 or |in20| > 2.")
    ctrl_jobs = [(400, images, dict(mu=10.0, kappa=4.0, band_axis=ax)) for ax in ("x", "y")]
    pwm_jobs, pwm_names = [], []
    for period, duty, ramp, off, mounts in E4_PWM:
        g = pwm_gain(768, period, duty, ramp, off)
        for ax in mounts:
            pwm_jobs.append((400, images, dict(mu=10.0, kappa=4.0, band_axis=ax, banding_shape="pwm",
                                               band_period=period, band_duty=duty, band_ramp=ramp, band_off=off)))
            pwm_names.append((f"E4_pwm_{period:.0f}_{duty}_{ramp:.0f}_{off}_{ax}", ax,
                              f"PWM {period:.0f} rows, duty {duty}, ramp {ramp:.0f}" + (f", off {off}" if off else "")
                              + f", mount {ax} (gain {g.min():.2f}-{g.max():.2f})"))
    for label, kw, mounts in E4_RULE_SINE:
        for ax in mounts:
            pwm_jobs.append((400, images, dict(mu=10.0, kappa=4.0, band_axis=ax, **kw)))
            pwm_names.append((f"E4_rule_{kw['band_period']:.0f}_{kw['banding']}_{ax}", ax, f"{label}, mount {ax}"))
    out = _map_banding(ctrl_jobs + pwm_jobs)
    ctrl = {}
    for ax, r in zip(("x", "y"), out[:2]):
        ctrl[ax] = r
        results[f"E4_pwm_control_{ax}"] = dict(r, _label=f"control, no banding, sensor rows {ax}")
        print(f" control, no banding, mount {ax}: raw A_tensor err mean {r['raw']['A_tensor']['err_mean']:+.2f}"
              f" sd {r['raw']['A_tensor']['err_sd']:+.2f}, B_merged err mean {r['raw']['B_merged']['err_mean']:+.2f}"
              f" sd {r['raw']['B_merged']['err_sd']:+.2f} | line vs raw: " + "  ".join(
                  f"{m} {_paired_text(r['_err']['line'][m], r['_err']['raw'][m], in20=True)}" for m in BANDING_METHODS)
              + f" | rule: excluded {r['_rule']['excluded']}, flagged {r['_rule']['flagged']}")
        print(_detect_text(r["_probe"], keys=("score_harm", "grad_frac", "band_common", "row_min"))
              + "  " + _dir_text(r["_dir"]))
    for i, ((key, ax, name), r) in enumerate(zip(pwm_names, out[2:])):
        if i == len(pwm_names) - sum(len(m) for _, _, m in E4_RULE_SINE):
            print(" The first part's sinusoidal and mains bands under the same rules (same mats and seed):")
        results[key] = dict(r, _label=name)
        _print_rule_condition(name, r, ctrl[ax]["_err"]["raw"], images)
    experiment_e4_dir(images, results, ctrl)


# Strand direction to the sensor rows (review cycle 4): layers (mu, kappa, mount); mu 10 kappa 4 is above
E4_DIR_LAYERS = ((20.0, 4.0, "x"), (30.0, 4.0, "x"), (45.0, 4.0, "x"), (55.0, 4.0, "x"), (60.0, 4.0, "x"),
                 (80.0, 4.0, "x"), (90.0, 4.0, "x"), (10.0, 3.0, "x"), (10.0, 2.5, "x"), (10.0, 2.0, "x"),
                 (10.0, 1.0, "x"), (0.0, 0.0, "x"), (80.0, 4.0, "y"))
# Band conditions of the strand-direction and wide-strand parts: (label, render arguments)
E4_DIR_BANDS = (
    ("sine 40 rows 10 %", dict(banding=0.10, band_period=40.0)),
    ("PWM 135/0.8/64", dict(banding_shape="pwm", band_period=135.0, band_duty=0.8, band_ramp=64.0)),
    ("PWM 270/0.8/64", dict(banding_shape="pwm", band_period=270.0, band_duty=0.8, band_ramp=64.0)),
    ("PWM 270/0.9/64", dict(banding_shape="pwm", band_period=270.0, band_duty=0.9, band_ramp=64.0)),
    ("PWM 270/0.5/64 near-dark", dict(banding_shape="pwm", band_period=270.0, band_duty=0.5, band_ramp=64.0)),
)
# Wide strands (width px, strands): length 5 x width, count scaled so that coverage matches the 24 px mats
E4_WIDE = ((36.0, 289), (48.0, 163))
E4_WIDE_LAYERS = ((90.0, 4.0, "x"), (10.0, 4.0, "y"), (10.0, 4.0, "x"))
E4_ROI_WIDTHS = (768, 512, 384, 256)


def _roi_crop(img, band_axis, w):
    """The ROI narrowed to w px along the sensor rows (rows run along x when band_axis is "y")."""
    return img[:, :w] if band_axis == "y" else img[:w, :]


def experiment_e4_dir(images, results, ctrl):
    print(f"\nE4  (cont.) ROI width and band detectors on mats without bands ({2 * images} images per layer, seed"
          " 400): share of shots at or above\n    the flag of band_common (>= "
          f"{BAND_COMMON_MIN}) and of grad_frac (>= {BAND_GRAD_MIN}), with the ROI narrowed along the sensor rows;"
          " darkest row\n    (row_min, full ROI width) minimum. Strands are 120 px long, so 256 px = 2 flake lengths.")
    for label, mu, kappa, ax in (("face layer mu 10, default mount", 10.0, 4.0, "x"),
                                 ("face layer mu 10, across the readout", 10.0, 4.0, "y"),
                                 ("core layer mu 90 kappa 4, default", 90.0, 4.0, "x"),
                                 ("core layer mu 90 kappa 16, default", 90.0, 16.0, "x"),
                                 ("random layer kappa 0, default", 0.0, 0.0, "x")):
        rng = np.random.default_rng(400)
        mets = {w: [] for w in E4_ROI_WIDTHS}
        for _ in range(2 * images):
            img, _t = render_mat(rng, mu=mu, kappa=kappa, band_axis=ax)
            for w in E4_ROI_WIDTHS:
                mets[w].append(banding_metrics(_roi_crop(img, ax, w), ax))
        row = {}
        for w in E4_ROI_WIDTHS:
            bc = np.array([m["band_common"] for m in mets[w]])
            gf = np.array([m["grad_frac"] for m in mets[w]])
            row[w] = {"band_common_share": float(np.mean(bc >= BAND_COMMON_MIN)), "band_common_max": float(bc.max()),
                      "grad_frac_share": float(np.mean(gf >= BAND_GRAD_MIN)), "grad_frac_max": float(gf.max()),
                      "row_min_min": float(min(m["row_min"] for m in mets[w]))}
        results[f"E4_roi_{mu:.0f}_{kappa:.0f}_{ax}"] = row
        print(f"  {label:<38} " + " | ".join(
            f"{w}: bc {100 * row[w]['band_common_share']:3.0f} % (max {row[w]['band_common_max']:.3f}) gf"
            f" {100 * row[w]['grad_frac_share']:3.0f} % row_min {row[w]['row_min_min']:.2f}" for w in E4_ROI_WIDTHS))

    print("\nE4  (cont.) Strand direction to the sensor rows: layers at mu (deg from MD) and kappa, mount x (default)"
          " or y, 8 images each,\n    paired against the same mats without bands. Per condition: changes from the"
          " control as mean, sd, in20 (images used), raw and under\n    the rule; dark = excluded for dark rows; flag"
          " = band_common flagged, then the condition's regime (per shot rows/along) and median psi and R;\n    bc ="
          " band_common median [min]; verdict ok = rule"
          " within 0.25 deg mean, 0.5 deg sd and 2 points in20 of the control, or excluded (random layer: sd and"
          " in20 only).")
    jobs, names = [], []
    for mu, kappa, ax in E4_DIR_LAYERS:
        base = dict(mu=mu, kappa=kappa, band_axis=ax)
        jobs.append((400, images, base))
        names.append((mu, kappa, ax, "control"))
        for label, kw in E4_DIR_BANDS:
            jobs.append((400, images, dict(base, **kw)))
            names.append((mu, kappa, ax, label))
    out = _map_banding(jobs)
    layer_ctrl = {}
    r_dist = {4.0: [d[1] for d in ctrl["x"]["_dir"]]}
    for (mu, kappa, ax, label), r in zip(names, out):
        key = f"E4_dir_{mu:.0f}_{kappa:g}_{ax}_{label}"
        results[key] = dict(r, _label=f"mu {mu:.0f}, kappa {kappa:g}, mount {ax}, {label}")
        if label == "control":
            layer_ctrl[(mu, kappa, ax)] = r
            if mu == 10.0 or kappa == 0.0:
                r_dist[kappa] = [d[1] for d in r["_dir"]]
            print(f" mu {mu:.0f}, kappa {kappa:g}, mount {ax}: control {_dir_text(r['_dir'])}; line vs raw: " + "  ".join(
                f"{m} {_paired_text(r['_err']['line'][m], r['_err']['raw'][m], in20=True)}" for m in BANDING_METHODS)
                + f" | flagged {r['_rule']['flagged']}")
            continue
        print(_compact_rule_line(label, r, layer_ctrl[(mu, kappa, ax)]["_err"]["raw"], images, kappa == 0.0))
    print(" R of A_tensor on the row-corrected copy per shot (no bands, mu 10; kappa 0: mu 0): " + "  ".join(
        f"kappa {k:g}: {np.median(v):.3f} [{min(v):.3f}, {max(v):.3f}]" for k, v in sorted(r_dist.items())))
    results["E4_dir_R"] = {f"{k:g}": v for k, v in r_dist.items()}
    dir_cost = [(f"mu 10 k 4 {ax}", ctrl[ax]) for ax in ("x", "y")] + [
        (f"mu {mu:.0f} k {kappa:g} {ax}", layer_ctrl[(mu, kappa, ax)]) for mu, kappa, ax in E4_DIR_LAYERS]
    _print_line_costs("strand-direction grid", dir_cost, results, "E4_line_cost_dir")

    print("\nE4  (cont.) Wide strands: length 5 x width, count scaled to the 24 px mats' coverage; the along regime's"
          f" window is {BAND_SMOOTH_FLAKE} flake widths\n    capped at {BAND_SMOOTH_MAX} rows. Same layout as above;"
          " the per-row correction is checked across the rows (mu 10, mount x); raw B\n    shows why B_merged is"
          " excluded on flagged shots.")
    jobs, names = [], []
    for width, n in E4_WIDE:
        for mu, kappa, ax in E4_WIDE_LAYERS:
            base = dict(mu=mu, kappa=kappa, band_axis=ax, width=width, length=5.0 * width, n=n)
            jobs.append((400, images, base))
            names.append((width, mu, kappa, ax, "control"))
            for label, kw in E4_DIR_BANDS:
                jobs.append((400, images, dict(base, **kw)))
                names.append((width, mu, kappa, ax, label))
    out = _map_banding(jobs)
    for (width, mu, kappa, ax, label), r in zip(names, out):
        results[f"E4_wide_{width:.0f}_{mu:.0f}_{ax}_{label}"] = dict(
            r, _label=f"strands {width:.0f} px, mu {mu:.0f}, mount {ax}, {label}")
        if label == "control":
            layer_ctrl[(width, mu, ax)] = r
            print(f" strands {width:.0f} px (window {band_window(width)} rows), mu {mu:.0f}, mount {ax}: control"
                  f" {_dir_text(r['_dir'])} | flagged {r['_rule']['flagged']}")
            continue
        print(_compact_rule_line(label, r, layer_ctrl[(width, mu, ax)]["_err"]["raw"], images))
    wide_cost = [(f"{width:.0f} px mu {mu:.0f} {ax}", layer_ctrl[(width, mu, ax)])
                 for width, _n in E4_WIDE for mu, _k, ax in E4_WIDE_LAYERS]
    _print_line_costs("wide strands", wide_cost, results, "E4_line_cost_wide")
    experiment_e4_boundary(images, results)


def _line_cost(r, variant="line"):
    """Change of A_tensor's mean (deg) when every image of a condition is corrected (variant "line": every row
    divided by its mean; "smooth": by the smoothed row means) instead of raw: (mean, SE) over the images."""
    ps = _paired_stats(r["_err"][variant]["A_tensor"], r["_err"]["raw"]["A_tensor"])
    return (float("nan"), float("nan")) if ps is None else (float(ps[0][0]), float(ps[1][0]))


def _print_line_costs(title, items, results, key):
    """Compact list of _line_cost on the controls (mats without bands): what dividing row by row costs A_tensor's
    mean on a clean mat, the error the rows regime adds on a flagged shot."""
    rows = {}
    for name, r in items:
        c, se = _line_cost(r)
        g = r["_regime"]
        rows[name] = {"mean": c, "se": se, "psi": g["psi"], "R": g["R"]}
    results[key] = rows
    print(f" Clean-mat cost of the row division on A_tensor's mean, {title} (control, line vs raw, mean ± SE; median"
          " psi, R): " + "; ".join(
        f"{name} {v['mean']:+.2f}±{v['se']:.2f} ({v['psi']:.0f}, {v['R']:.3f})" for name, v in rows.items()))


# Regime boundary (review cycle 5): layers in mount x at mu (deg from MD) x kappa, under three of E4_DIR_BANDS, and
# the wide strands of E4_WIDE (kappa 4) at the mid angles the wide-strand grid lacks
E4_BOUND_MUS = (40.0, 45.0, 50.0, 55.0, 60.0)
E4_BOUND_KAPPAS = (2.5, 3.0, 4.0)
E4_BOUND_WIDE_MUS = (30.0, 40.0, 45.0, 50.0)
E4_BOUND_BANDS = tuple(b for b in E4_DIR_BANDS if b[0] in ("sine 40 rows 10 %", "PWM 135/0.8/64", "PWM 270/0.9/64"))


def experiment_e4_boundary(images, results):
    print(f"\nE4  (cont.) Regime boundary: layers in mount x at mu {', '.join(f'{m:.0f}' for m in E4_BOUND_MUS)}"
          f" (psi about {', '.join(f'{90 - m:.0f}' for m in E4_BOUND_MUS)}) and kappa"
          f" {', '.join(f'{k:g}' for k in E4_BOUND_KAPPAS)}, then\n    strands of"
          f" {' and '.join(f'{w:.0f}' for w, _n in E4_WIDE)} px (as in the wide-strand part, kappa 4) at mu"
          f" {', '.join(f'{m:.0f}' for m in E4_BOUND_WIDE_MUS)}; {images} images each, paired against the same mats"
          " without bands;\n    A_tensor only (B_merged is excluded on every flagged shot whatever the regime). The app"
          " decides the regime once per run from its\n    first flagged shots, so a layer near the boundary may get"
          " either: A is evaluated raw and with the regime forced, rows (every row\n    divided by its mean) and along"
          f" (row means smoothed over {BAND_SMOOTH_FLAKE} flake widths, at most {BAND_SMOOTH_MAX} rows; A excluded"
          f" when row_min < {BAND_SMOOTH_ROW_MIN}), each as\n    changes mean, sd, in20 (images used) with its verdict,"
          f" then the regime the rule picks ({_regime_rule_text()}) and\n    its verdict. Control line: median psi"
          " and R, and the clean-mat cost of each correction on A's mean (rows = line vs raw, along =\n    smoothed vs"
          " raw; mean ± SE).")
    layers = [(24.0, None, mu, kappa) for mu in E4_BOUND_MUS for kappa in E4_BOUND_KAPPAS] + [
        (width, n, mu, 4.0) for width, n in E4_WIDE for mu in E4_BOUND_WIDE_MUS]
    jobs, names = [], []
    for width, n, mu, kappa in layers:
        base = dict(mu=mu, kappa=kappa, band_axis="x", methods=("A_tensor",), forced=True)
        if n is not None:
            base.update(width=width, length=5.0 * width, n=n)
        jobs.append((400, images, base))
        names.append((width, mu, kappa, "control"))
        for label, kw in E4_BOUND_BANDS:
            jobs.append((400, images, dict(base, **kw)))
            names.append((width, mu, kappa, label))
    out = _map_banding(jobs)
    ctrl, costs = {}, []
    tally = {w: {"rule": 0, "rule_rows": 0, "rule_along": 0, "n": 0} for w in ("24", "wide")}
    worst = {}

    def txt(r, v, c):
        p = _paired_means(r["_err"][v]["A_tensor"], c["_err"]["raw"]["A_tensor"])
        n_used = sum(e is not None for e in r["_err"][v]["A_tensor"])
        return "      excluded      " if p is None else f"{p[0]:+5.2f} {p[1]:+5.2f} {p[2]:+5.1f} ({n_used})"

    for (width, mu, kappa, label), r in zip(names, out):
        tag = f"{width:.0f}px_{mu:.0f}_{kappa:g}"
        results[f"E4_bound_{tag}_{label}"] = dict(r, _label=f"strands {width:.0f} px, mu {mu:.0f}, kappa {kappa:g},"
                                                            f" mount x, {label}")
        if label == "control":
            ctrl[(width, mu, kappa)] = r
            costs.append((f"{width:.0f} px mu {mu:.0f} k {kappa:g}", r))
            cr, cs = _line_cost(r), _line_cost(r, "smooth")
            print(f" strands {width:.0f} px, mu {mu:.0f}, kappa {kappa:g}: control {_dir_text(r['_dir'])}; clean-mat"
                  f" cost of A on the mean: rows {cr[0]:+.2f}±{cr[1]:.2f}, along {cs[0]:+.2f}±{cs[1]:.2f}")
            continue
        c = ctrl[(width, mu, kappa)]
        group = "24" if width == 24.0 else "wide"
        oks = {v: _rule_ok(r, c["_err"]["raw"], variant=v) for v in ("rule", "rule_rows", "rule_along")}
        tally[group]["n"] += 1
        for v, ok in oks.items():
            tally[group][v] += int(ok)
            p = _paired_means(r["_err"][v]["A_tensor"], c["_err"]["raw"]["A_tensor"])
            if p is not None and ((group, v) not in worst or abs(p[0]) > abs(worst[(group, v)][0])):
                worst[(group, v)] = (float(p[0]), f"{width:.0f} px mu {mu:.0f} k {kappa:g} {label}")
        g = r["_regime"]
        bc = [p["band_common"] for p in r["_probe"]]
        print(f"  {label:<18} raw A {txt(r, 'raw', c)} | rows A {txt(r, 'rule_rows', c)}"
              f" {'ok  ' if oks['rule_rows'] else 'FAIL'} | along A {txt(r, 'rule_along', c)}"
              f" {'ok  ' if oks['rule_along'] else 'FAIL'} | rule {g['regime']:<5} {'ok  ' if oks['rule'] else 'FAIL'}"
              f" (psi {g['psi']:4.1f} R {g['R']:.3f}) | flag {r['_rule']['flagged']} bc {np.median(bc):.3f}"
              f" row_min {min(p['row_min'] for p in r['_probe']):.2f}")
    results["E4_bound_summary"] = {grp: dict(t, worst_mean={v: list(worst[(grp, v)]) for v in
                                                            ("rule", "rule_rows", "rule_along") if (grp, v) in worst})
                                   for grp, t in tally.items()}
    for grp, label in (("24", "24 px layers"), ("wide", "wide strands")):
        t = tally[grp]
        print(f" Regime boundary summary, {label}: within tolerance (or excluded) under the regime the rule picks"
              f" {t['rule']}/{t['n']}, forced rows {t['rule_rows']}/{t['n']}, forced along {t['rule_along']}/{t['n']};"
              " largest change of the mean: " + ", ".join(
                  f"{v} {worst[(grp, v)][0]:+.2f} ({worst[(grp, v)][1]})" for v in ("rule", "rule_rows", "rule_along")
                  if (grp, v) in worst))
    _print_line_costs("boundary layers", costs, results, "E4_line_cost_bound")


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


def fl_frames(rng, tab, F, T_r, frame_s, surface, noise=5e-4, reverse=False, exposure=FL_EXPOSURE_S,
              lamp_b=None):
    """Row-mean profiles (n_frames, FL_ROWS) of frames whose row r starts its exposure at
    t0 + k frame_s + r T_r / FL_ROWS (reverse: rows read bottom to top), under flicker `tab` at F Hz.

    lamp_b (delay_s, grad, turned): a second lamp with the same waveform `delay_s` later (another phase of
    the three-phase mains) lights the surface too; lamp A's share is 50 % +- grad / 2, changing linearly
    across the view (more lamp A at the top of the sensor; turned: the phone turned 180 deg, so more lamp A
    at the bottom)."""
    y = np.arange(FL_ROWS, dtype=np.float64)
    rt = ((FL_ROWS - 1 - y) if reverse else y) * T_r / FL_ROWS
    t0 = rng.uniform(0.0, 1.0)
    n = surface.shape[0]
    out = np.empty((n, FL_ROWS))
    if lamp_b is not None:
        delay_s, grad, turned = lamp_b
        c = (FL_ROWS - 1) / 2.0
        wa = 0.5 * (1.0 - grad * (y - c) / c * (-1.0 if turned else 1.0))
    for k in range(n):
        light = flicker_light(tab, F, t0 + k * frame_s + rt, exposure)
        if lamp_b is not None:
            light = wa * light + (1.0 - wa) * flicker_light(tab, F, t0 + k * frame_s + rt + delay_s, exposure)
        out[k] = surface[k] * light
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


def readout_phase(prof, roi, F, frame_s, strip=32, window="hann", details=False):
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
    coef = np.linalg.lstsq(a, ph * w, rcond=None)[0]
    slope = float(coef[0])
    t_r, direction = abs(slope) * FL_ROWS / (2.0 * math.pi * F), (1 if slope > 0 else -1)
    if not details:
        return t_r, direction
    # |X|^2-weighted RMS residual of the phase line (rad): small when one flicker with one phase per row
    # lights the view, large when the bin holds noise or the phase does not grow linearly with the row
    res = ph - (slope * centres + float(coef[1]))
    resid = math.sqrt(float((w ** 2 * res ** 2).sum()) / max(float((w ** 2).sum()), 1e-300))
    return t_r, direction, {"resid_rad": resid}


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
FL_ROI_OFF = (80, 1580)                             # 1,500 rows, 250 rows above the centre (E13h)

# Light-check acceptance and readout-test checks (E13a cont., E13g, E13h; review cycle 4)
FL_ACCEPT_RATIO = 3.0        # frequency accepted when the index is >= this x the median of the other bins ...
FL_ACCEPT_MIN = 0.01         # ... and >= this minimum index (steady light on a shaking or moving surface)
FL_READOUT_MIN_INDEX = 0.01  # readout test runs only from this light-check index (accepted frequency)
FL_TR_MARGIN_S = 0.002       # readout check: T_r <= frame duration (1/27 s) - this margin
FL_AMP_BAND = (0.8, 1.2)       # readout check: readout burst's bin amplitude / ((2/pi) x light-check index)
FL_RESID_MAX = 0.25          # readout check: |X|^2-weighted RMS residual of the phase line (rad)


def fl_accepted(lc, min_index=FL_ACCEPT_MIN):
    """Light check frequency accepted: index >= FL_ACCEPT_RATIO x the other bins' median and >= min_index."""
    return lc["index"] >= FL_ACCEPT_RATIO * lc["floor"] and lc["index"] >= min_index


def fl_readout_test(rng, tab, F, tr_s, drift=0.0, shake=0.0, tex=0.01, reverse=False, lamp_b=None, roi=FL_ROI):
    """Simulated readout test (design 6.16) under the light `tab` at F Hz.

    A light check burst at the run's exposure gives the index and the frequency F_c; then the readout burst
    (27 frames at 1/27 s, exposure 1/(2 F_c)) is taken twice, the second time with the phone turned 180 deg
    (a scene phase gradient, lamp_b's mix, flips sign in sensor coordinates; a single light is unchanged).
    lamp_b (delay_s, grad) as fl_frames; roi: sensor rows of the ROI (the same rows in both bursts). Returns (light check, [per readout burst: T_r s, direction, phase-line
    residual rad, bin amplitude at F_c over (2/pi) x the light check's index]). An exposure of 1/(2F)
    attenuates the fundamental by sinc(1/2) = 2/pi, so the ratio is about 1 for a light at F_c.
    """
    surf = fl_surface(rng, FL_BURST, drift, shake, tex)
    lc = light_check(fl_frames(rng, tab, F, tr_s, 1.0 / FL_BURST, surf, reverse=reverse,
                               lamp_b=None if lamp_b is None else (lamp_b[0], lamp_b[1], False)), roi)
    fc = float(lc["hz"])
    runs = []
    for turned in (False, True):
        lb = None if lamp_b is None else (lamp_b[0], lamp_b[1], turned)
        surf = fl_surface(rng, FL_BURST, drift, shake, tex)
        prof = fl_frames(rng, tab, F, tr_s, 1.0 / FL_BURST, surf, reverse=reverse, exposure=1.0 / (2.0 * fc),
                         lamp_b=lb)
        t_r, d, det = readout_phase(prof, roi, fc, 1.0 / FL_BURST, details=True)
        amp = light_check(prof, roi)["by_bin"][lc["hz"]]
        runs.append({"t_r": t_r, "dir": d, "resid": det["resid_rad"],
                     "amp_ratio": amp / (2.0 / math.pi * max(lc["index"], 1e-12))})
    return lc, runs


def fl_checks(lc, run):
    """Readout-test checks on one readout burst: (T_r plausible, amplitude ratio in band, residual small)."""
    return (run["t_r"] <= 1.0 / FL_BURST - FL_TR_MARGIN_S,
            FL_AMP_BAND[0] <= run["amp_ratio"] <= FL_AMP_BAND[1],
            run["resid"] <= FL_RESID_MAX)


def _e13_acceptance(res):
    """E13a (cont.): frequency identification and acceptance per E13a case, from the stored bursts."""
    print(f"\n  E13a (cont.) Light check per case: F ok = the strongest bin is the light's frequency; accepted ="
          f" index >= {FL_ACCEPT_RATIO:g} x the other bins'\n  median (3x), and also >= {FL_ACCEPT_MIN} (min) or"
          f" >= {FL_READOUT_MIN_INDEX} (the readout test's gate); right F = accepted with the right frequency."
          "\n  Steady light: every acceptance is a false alarm.")
    for key, v in res.items():
        if not key.startswith("E13a_"):
            continue
        idx, fl, hz, ft = v["index"], v["floor"], v["hz"], v["f_true"]
        steady = "depth" not in v
        a3 = [i >= FL_ACCEPT_RATIO * f for i, f in zip(idx, fl)]
        amin = [a and i >= FL_ACCEPT_MIN for a, i in zip(a3, idx)]
        agate = [a and i >= FL_READOUT_MIN_INDEX for a, i in zip(a3, idx)]
        right = sum(int(a and h == t) for a, h, t in zip(amin, hz, ft))
        v["accepted_3x"], v["accepted_min"], v["accepted_gate"] = sum(a3), sum(amin), sum(agate)
        fok = "  -  " if steady else f"{v['freq_ok']:>2}/{v['n']}"
        print(f"  {key[5:]:<66} F ok {fok} | accepted 3x {sum(a3):>2}, min {sum(amin):>2}, gate {sum(agate):>2}"
              + ("" if steady else f" | right F {right:>2}") + f"  (of {v['n']})")


def _e13_readout_checks(images, res):
    """E13g / E13h: readout-test gate and checks on valid lights, then on lights that fool the test."""
    rng = np.random.default_rng(1310)
    waves = FL_WAVES[1:3] + (("sine 1 %", "sine", 0.01, 0.0, 0.0, False),
                             ("sine 1.5 %", "sine", 0.015, 0.0, 0.0, False)) + FL_WAVES[3:]
    print("\n  E13g Readout test as run: light check (run exposure), then two readout bursts at 1/(2F) (the second"
          " with the phone turned\n  180 deg), T_r 5-25 ms, mains 50 and 60 Hz, nominal and 0.1 Hz above and"
          " below, still and 1 px shake surfaces.\n  Per case over the bursts the light check accepts (3x and"
          f" >= the gate {FL_READOUT_MIN_INDEX}): max |T_r error| % of one burst and of the mean of the two;"
          "\n  amplitude ratio = readout burst's bin / ((2/pi) x index); residual = phase-line fit (rad);"
          f" fails = bursts failing\n  T_r <= {1000.0 / FL_BURST - 1000.0 * FL_TR_MARGIN_S:.1f} ms / ratio in"
          f" [{FL_AMP_BAND[0]}, {FL_AMP_BAND[1]}] / residual <= {FL_RESID_MAX}.")
    gate_rows = []                                   # (index, accepted 3x, surface, |error| one burst)
    ratios, resids = [], []
    for wl, kind, depth, tau, duty, half in waves:
        for sl, drift, shake, tex in FL_SURFACES[:2]:
            n = acc = 0
            e1, e2, rr, rs, fails = [], [], [], [], [0, 0, 0]
            for f0 in (50, 60):
                Fn = float(f0 if half else 2 * f0)
                for df in (0.0, 0.1, -0.1):
                    F = Fn * (f0 + df) / f0
                    tab = flicker_table(kind, F, depth, tau, duty)
                    for i, tr in enumerate(FL_TR_MS):
                        lc, runs = fl_readout_test(rng, tab, F, tr / 1000.0, drift, shake, tex, reverse=bool(i % 2))
                        n += 1
                        err = 100.0 * (runs[0]["t_r"] / (tr / 1000.0) - 1.0)
                        ok3 = lc["index"] >= FL_ACCEPT_RATIO * lc["floor"] and lc["hz"] == int(Fn)
                        gate_rows.append((lc["index"], ok3, sl, abs(err)))
                        if not (fl_accepted(lc, FL_READOUT_MIN_INDEX) and lc["hz"] == int(Fn)):
                            continue
                        acc += 1
                        e1.append(err)
                        e2.append(100.0 * (0.5 * (runs[0]["t_r"] + runs[1]["t_r"]) / (tr / 1000.0) - 1.0))
                        rr.append(runs[0]["amp_ratio"])
                        rs.append(runs[0]["resid"])
                        for j, ok in enumerate(fl_checks(lc, runs[0])):
                            fails[j] += int(not ok)
            ratios += rr
            resids += rs
            res[f"E13g_{wl}_{sl}"] = {"n": n, "accepted": acc, "err_one": e1, "err_mean2": e2, "amp_ratio": rr,
                                      "resid": rs, "fails": fails}
            if acc == 0:
                print(f"  {wl:<27} | {sl:<33} | accepted 0/{n}: no readout test")
                continue
            print(f"  {wl:<27} | {sl:<33} | accepted {acc:>2}/{n} | T_r err max one {np.max(np.abs(e1)):5.2f}"
                  f" mean of 2 {np.max(np.abs(e2)):5.2f} | ratio [{min(rr):.3f}, {max(rr):.3f}] resid max"
                  f" {max(rs):.3f} | fails {fails[0]}/{fails[1]}/{fails[2]}")
    print(f"  valid bursts over all cases: ratio [{min(ratios):.3f}, {max(ratios):.3f}], residual max"
          f" {max(resids):.3f} rad")
    print("  Gate on the light-check index (accepted 3x, right F): bursts and max |T_r error| % of one burst at"
          " the readout exposure")
    for sl in (FL_SURFACES[0][0], FL_SURFACES[1][0]):
        line = []
        for g in (0.005, 0.01, 0.015, 0.02):
            sel = [e for i, ok, s, e in gate_rows if ok and s == sl and i >= g]
            line.append(f">= {g}: {len(sel):>3} bursts, max {max(sel) if sel else float('nan'):6.2f}")
        print(f"    {sl:<33} " + " | ".join(line))
    res["E13g_gate"] = [list(r) for r in gate_rows]

    print("\n  E13h Lights that fool the readout test (still surface, 1 % texture): kHz PWM near a light-check bin"
          " (duty 0.8), and two\n  lamps (full-wave rectified) on mains phases 120 / 240 deg apart whose share"
          " changes linearly across the view.\n  accepted = light check 3x and >= the gate; T_r = one readout"
          " burst (range over T_r 5-25 ms or 8-16 ms); fails per check as E13g;\n  mean of 2 = with the phone"
          " turned 180 deg for the second burst.")
    for f_pwm in (1000.0, 1100.0, 1200.0, 1234.5, 2160.0):
        tab = flicker_table("square", f_pwm, duty=0.8)
        rows = []
        for i, tr in enumerate(FL_TR_MS):
            lc, runs = fl_readout_test(rng, tab, f_pwm, tr / 1000.0, reverse=bool(i % 2))
            rows.append((tr, lc, runs))
        acc = [r for r in rows if fl_accepted(r[1], FL_READOUT_MIN_INDEX)]
        hz = sorted({r[1]["hz"] for r in acc})
        fails = [sum(int(not fl_checks(r[1], r[2][0])[j]) for r in acc) for j in range(3)]
        caught = sum(int(not all(fl_checks(r[1], r[2][0]))) for r in acc)
        res[f"E13h_pwm_{f_pwm}"] = [{"tr_ms": tr, "index": lc["index"], "floor": lc["floor"], "hz": lc["hz"],
                                     "t_r_ms": [1000.0 * x["t_r"] for x in runs],
                                     "amp_ratio": [x["amp_ratio"] for x in runs],
                                     "resid": [x["resid"] for x in runs]} for tr, lc, runs in rows]
        idx = [r[1]["index"] for r in rows]
        txt = (f"accepted {len(acc)}/{len(rows)} as {hz} Hz" if acc else f"accepted 0/{len(rows)}")
        if acc:
            t_est = [1000.0 * r[2][0]["t_r"] for r in acc]
            rat = [r[2][0]["amp_ratio"] for r in acc]
            rs = [r[2][0]["resid"] for r in acc]
            txt += (f" | T_r {min(t_est):6.1f}-{max(t_est):6.1f} ms for 5-25 | ratio [{min(rat):.3f}, {max(rat):.3f}]"
                    f" resid [{min(rs):.3f}, {max(rs):.3f}] | fails {fails[0]}/{fails[1]}/{fails[2]}, caught"
                    f" {caught}/{len(acc)}")
        print(f"  PWM {f_pwm:7.1f} Hz: index {min(idx):.4f}-{max(idx):.4f} | {txt}")
    for f0 in (50, 60):
        F = 2.0 * f0
        tab = flicker_table("rect", F)
        for shift in (120.0, 240.0):
            for pct in (2.5, 5.0, 10.0):
                e1, e2, e2_off, rat, rs, fails, n_acc = [], [], [], [], [], [0, 0, 0], 0
                for i, tr in enumerate(FL_TR_MS):
                    lamp_b = (shift / 360.0 / f0, 2.0 * pct / 100.0)
                    lc, runs = fl_readout_test(rng, tab, F, tr / 1000.0, reverse=bool(i % 2), lamp_b=lamp_b)
                    # the same with the ROI 250 rows off the frame centre: turning the phone moves the ROI to
                    # another part of the scene, so the two phase gradients no longer cancel exactly
                    _, runs_off = fl_readout_test(rng, tab, F, tr / 1000.0, reverse=bool(i % 2), lamp_b=lamp_b,
                                                  roi=FL_ROI_OFF)
                    if not fl_accepted(lc, FL_READOUT_MIN_INDEX):
                        continue
                    n_acc += 1
                    e1.append(100.0 * (runs[0]["t_r"] / (tr / 1000.0) - 1.0))
                    e2.append(100.0 * (0.5 * (runs[0]["t_r"] + runs[1]["t_r"]) / (tr / 1000.0) - 1.0))
                    e2_off.append(100.0 * (0.5 * (runs_off[0]["t_r"] + runs_off[1]["t_r"]) / (tr / 1000.0) - 1.0))
                    rat.append(runs[0]["amp_ratio"])
                    rs.append(runs[0]["resid"])
                    for j, ok in enumerate(fl_checks(lc, runs[0])):
                        fails[j] += int(not ok)
                res[f"E13h_lamps_{f0}_{shift:.0f}_{pct}"] = {"err_one": e1, "err_mean2": e2, "err_mean2_off": e2_off,
                                                             "amp_ratio": rat, "resid": rs, "fails": fails,
                                                             "accepted": n_acc}
                print(f"  two lamps, mains {f0} Hz, lamp B {shift:3.0f} deg later, lamp A 50 % +-{pct:4.1f} %:"
                      f" accepted {n_acc}/{len(FL_TR_MS)} | T_r err one [{min(e1):+6.2f}, {max(e1):+6.2f}] %"
                      f" mean of 2 [{min(e2):+5.2f}, {max(e2):+5.2f}] %, ROI off centre [{min(e2_off):+5.2f},"
                      f" {max(e2_off):+5.2f}] % | ratio [{min(rat):.3f}, {max(rat):.3f}] resid max {max(rs):.3f}"
                      f" | fails {fails[0]}/{fails[1]}/{fails[2]}")


def _e13_drift50(res):
    """E13i: share of the run's frames whose brightness drift exceeds 10 % under 50 Hz mains flicker."""
    rng = np.random.default_rng(1320)
    print("\n  E13i Brightness drift under 50.02 Hz mains (sine flicker at 100.04 Hz), 1/30 s frames over 60 s"
          " (1,800 frames), still\n  surface without texture, vignetting 0.3. Reference = per strip, the mean over"
          " every frame of the run's first second (30 frames).\n  Share of frames whose RMS over strips of"
          " |strip mean rel - 1| exceeds 10 % (T_r 8, 12, 16 ms), and that RMS's range.")
    for depth in (0.10, 0.13, 0.15, 0.20, 0.30):
        for roi_h in (500, 1500):
            roi = ((FL_ROWS - roi_h) // 2, (FL_ROWS - roi_h) // 2 + roi_h)
            line, out = [], []
            for tr in (8.0, 12.0, 16.0):
                tab = flicker_table("sine", 100.04, depth)
                surf = fl_surface(rng, 1800, 0.0, 0.0, 0.0, vign=0.3)
                prof = fl_frames(rng, tab, 100.04, tr / 1000.0, 1.0 / 30.0, surf)
                series, _ = fl_strips(prof, roi)
                rel = series / series[:30].mean(axis=0) - 1.0
                rms = np.sqrt(np.mean(rel ** 2, axis=1))
                share = float(np.mean(rms > 0.10))
                out.append({"tr_ms": tr, "share": share, "rms_min": float(rms.min()), "rms_max": float(rms.max())})
                line.append(f"T_r {tr:2.0f} ms: {100 * share:5.1f} % (RMS {100 * rms.min():4.1f}-{100 * rms.max():4.1f} %)")
            res[f"E13i_{depth}_{roi_h}"] = out
            print(f"  sine {100 * depth:2.0f} %, ROI {roi_h:4d} rows | " + " | ".join(line))


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
            hzs, f_true = [], []
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
                        hzs.append(lc["hz"])
                        f_true.append(int(F))
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
                res[f"E13a_{wl}_{sl}"] = {"index": idx, "floor": floor, "n": n, "hz": hzs, "f_true": f_true,
                                          "tr_err_pct": errs}
                print(f"  {wl:<27} | {sl:<37} | index {np.median(idx):.4f} [{min(idx):.4f}, {max(idx):.4f}]"
                      f" floor {np.median(floor):.4f}  (no flicker: index = noise level)")
                continue
            e, e_dt = np.asarray(errs), np.asarray(errs_dt)
            key = f"E13a_{wl}_{sl}"
            res[key] = {"depth": dep, "fundamental": fund, "index": idx, "index_rel_err": rel,
                        "freq_ok": hz_ok, "n": n, "hz": hzs, "f_true": f_true,
                        "floor": floor, "whole_roi_index": whole, "tr_err_pct": errs, "tr_err_pct_detrend": errs_dt,
                        "dir_ok": dir_ok}
            print(f"  {wl:<27} | {sl:<37} | depth {dep:4.2f} exp {fund:.4f} | index {np.median(idx):.4f}"
                  f" [{min(idx):.4f}, {max(idx):.4f}] /exp-1 [{100 * min(rel):+5.1f}, {100 * max(rel):+5.1f}] %"
                  f" floor {np.median(floor):.4f} whole-ROI {np.median(whole):.4f}"
                  f" | F ok {hz_ok}/{n} | T_r err % Hann [{e.min():+6.2f}, {e.max():+6.2f}] detrend"
                  f" [{e_dt.min():+6.2f}, {e_dt.max():+6.2f}] | dir {dir_ok}/{n}")

    _e13_acceptance(res)

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
    _e13_readout_checks(images, res)
    _e13_drift50(res)
    results["E13"] = res


# ----------------------------------------------------------------------------------------------
# E14 image noise (conditions forecast: the line speed sets the shutter, the light then the ISO)
# ----------------------------------------------------------------------------------------------

E14_SEED = 1400
E14_BASE = 0.012                                 # the lab's baseline noise (every other experiment)
E14_WHITE = (0.006, 0.0085, 0.012, 0.017, 0.025, 0.035, 0.05, 0.071, 0.10)   # white noise sigma (steps of ~sqrt 2)
E14_CORR = (0.017, 0.025, 0.035, 0.05, 0.071, 0.10)   # correlated variant (as left by ISP denoising)
E14_CORR_BLUR = 0.7                              # its Gaussian filter sigma (px)
E14_HP_FLAKES = 2.0                              # high-pass contrast: Gaussian low-pass of this many flake widths
E14_LAYERS = (("face mu 10 kappa 4", 10.0, 4.0), ("face mu 10 kappa 2", 10.0, 2.0),
              ("core mu 90 kappa 4", 90.0, 4.0), ("random kappa 0", 0.0, 0.0))
E14_LIM = (0.25, 0.5, 2.0)                       # tolerances: mean deg, spread deg, in20 points
E14_CASES = tuple(("white", s) for s in E14_WHITE) + tuple(("corr", s) for s in E14_CORR)


def highpass_contrast(img, wset):
    """The contrast the conditions forecast measures: standard deviation of img minus its Gaussian low-pass of
    sigma E14_HP_FLAKES flake widths (px), so that slow shading and the mat's coarse layout do not count."""
    f = img.astype(np.float32)
    return float((f - cv2.GaussianBlur(f, (0, 0), E14_HP_FLAKES * wset)).std())


def run_noise_condition(seed, images, cases=E14_CASES, **mat):
    """A_tensor and B_merged (estimator settings of run_condition) on `images` mats from one seeded generator, each
    mat at every noise case (kind "white" or "corr", sigma): the mat is rendered once and the cases are made from
    the same standard normal field (render_mat's noise_field and add_noise; the same images as rendering each case
    with its own noise), so the cases pair per image. Returns {"contrast": [standard deviation of the noiseless
    image per image], "contrast_hp": [highpass_contrast of the noiseless image per image], "cases": {(kind,
    sigma): {"_err": {method: [(mean err, sd err, in20 err) per image, None when empty]}, "b_count": [B_merged
    samples per image], "_probe": [banding_metrics per image]}}}."""
    rng = np.random.default_rng(seed)
    wset = float(mat.get("width", 24.0))
    axis = mat.get("band_axis", "x")
    mat = {k: v for k, v in mat.items() if k not in ("noise", "noise_blur")}
    out = {"contrast": [], "contrast_hp": [],
           "cases": {c: {"_err": {m: [] for m in BANDING_METHODS}, "b_count": [], "_probe": []} for c in cases}}
    for _ in range(images):
        clean, field = [], []
        _img, truth = render_mat(rng, clean=clean, noise_field=field, **mat)
        out["contrast"].append(float(clean[0].std()))
        out["contrast_hp"].append(highpass_contrast(clean[0], wset))
        ts = axial_stats(truth["theta"][truth["visible_frac"] >= 0.25])
        for kind, sig in cases:
            img = add_noise(clean[0], field[0], sig, E14_CORR_BLUR if kind == "corr" else 0.0)
            co = out["cases"][(kind, sig)]
            co["_probe"].append(banding_metrics(img, axis))
            thb = estimate_segments_merged(img, min_len=1.5 * wset, max_gap=2.0 * wset)[0]
            co["b_count"].append(int(len(thb)))
            for m, (th, w) in (("A_tensor", estimate_tensor(img, sigma_i=0.25 * wset)), ("B_merged", (thb, None))):
                ms = axial_stats(th, w)
                co["_err"][m].append([axial_diff(ms["mean"], ts["mean"]), ms["sd"] - ts["sd"],
                                      ms["in20"] - ts["in20"]] if ms.get("n", 0) and ts.get("n", 0) else None)
    return out


def _noise_job(args):
    """Worker for _map_noise: (seed, images, render arguments) -> run_noise_condition result."""
    seed, images, kw = args
    return run_noise_condition(seed, images, **kw)


def _map_noise(jobs):
    """run_noise_condition over (seed, images, render arguments) jobs on up to 4 processes, order kept; each job
    seeds its own generator, so the results do not depend on the process count."""
    procs = min(4, os.cpu_count() or 1, len(jobs))
    if procs <= 1:
        return [_noise_job(j) for j in jobs]
    import multiprocessing
    with multiprocessing.get_context("fork").Pool(procs) as pool:
        return pool.map(_noise_job, jobs, chunksize=1)


def _paired_stats(errs, ctrl):
    """Paired change from the control: (mean, SE) arrays over (mean, sd, in20), or None when all excluded (SE 0
    with one image)."""
    d = np.asarray([[a - b for a, b in zip(e, c)] for e, c in zip(errs, ctrl) if e is not None and c is not None])
    if d.size == 0:
        return None
    se = d.std(axis=0, ddof=1) / math.sqrt(len(d)) if len(d) >= 2 else np.zeros(3)
    return d.mean(axis=0), se


E14_PARTS = ("mean", "sd", "in20")


def _e14_limit(rs, base, m, kind, frac, random_layer):
    """The noise limit of one method by the forecast's rule: scanning the sigmas of `kind` above the baseline
    upwards, the largest sigma up to which every paired change (point estimate) stays within frac x the tolerances
    (mean ignored on a random layer). Returns {"sigma": that sigma (the baseline when the first step leaves),
    "exit": the first sigma that leaves (None = none within the grid), "part": the part that leaves, "fragile":
    True when the decision rests on a change within one SE of its threshold (the last sigma inside could be
    outside, or the exit could be inside)}."""
    parts = range(1, 3) if random_layer else range(3)
    thr = [frac * x for x in E14_LIM]
    last, fragile = E14_BASE, False
    for sig in sorted(s for k, s in E14_CASES if k == kind and s > E14_BASE):
        ps = _paired_stats(rs[(kind, sig)]["_err"][m], base["_err"][m])
        if ps is None:
            return {"sigma": last, "exit": sig, "part": "excluded", "fragile": fragile}
        p, se = ps
        out = [j for j in parts if abs(p[j]) > thr[j]]
        if out:
            fragile = fragile or all(abs(p[j]) - se[j] <= thr[j] for j in out)
            return {"sigma": last, "exit": sig, "part": "+".join(E14_PARTS[j] for j in out), "fragile": fragile}
        last = sig
        fragile = any(abs(p[j]) + se[j] > thr[j] for j in parts)
    return {"sigma": last, "exit": None, "part": None, "fragile": fragile}


def _e14_limit_text(lim, contrast):
    """CNR (sigma) of a limit; "<=" when no tested sigma left the band (the limit lies at or below that CNR), "*"
    when fragile, then where and on which part it leaves."""
    cnr = contrast / lim["sigma"]
    t = f"{'<=' if lim['exit'] is None else ''}{cnr:.1f}{'*' if lim['fragile'] else ''} ({lim['sigma']:.3f})"
    return t + ("" if lim["exit"] is None else f" out at {lim['exit']:.3f} {lim['part']}")


def experiment_e14(images, results):
    n_img = 2 * images
    print(f"\nE14 Image noise (conditions forecast): Gaussian noise sigma in lab units (1 = full scale), mount x,"
          f" seed {E14_SEED},\n    {n_img} images per condition (twice the run's count, for smaller standard errors),"
          " each mat rendered once and seen at every sigma\n    (the same strands and the same normal field)."
          f" Changes from sigma {E14_BASE} (the lab's baseline), mean ± SE over the images of the paired\n    "
          "difference (deg; in20 in points). contrast = standard deviation of the noiseless image; high-pass ="
          " the same after subtracting\n    a Gaussian low-pass of sigma"
          f" {E14_HP_FLAKES:g} flake widths (48 px), as the app measures it (medians over images); CNR = high-pass"
          " contrast / sigma.\n    B n = B_merged samples per image (mean). bc = share of shots flagged by"
          f" band_common (>= {BAND_COMMON_MIN}) on these unbanded mats; row_min =\n    darkest row (minimum)."
          f" corr = the noise field filtered with a Gaussian of sigma {E14_CORR_BLUR} px and rescaled to the same"
          " sigma (ISP denoising),\n    paired against the same white baseline. Tolerances: 0.25 deg mean, 0.5 deg"
          " spread, 2 points in20 (random layer: spread and in20 only).\n    Limits (one rule): Good = the"
          " smallest CNR (largest sigma) up to which every change stays within half of the tolerances, Poor = within"
          "\n    the tolerances, scanning sigma upwards from the baseline on the point estimates; <= = no tested sigma"
          " left the band; * = fragile\n    (the deciding change is within one SE of its threshold); out at = the"
          " first sigma that leaves, and on which part.")
    jobs = [(E14_SEED, n_img, dict(mu=mu, kappa=kappa, band_axis="x")) for _name, mu, kappa in E14_LAYERS]
    summary, worst = {}, {}
    for (name, mu, kappa), lr in zip(E14_LAYERS, _map_noise(jobs)):
        rs = lr["cases"]
        base = rs[("white", E14_BASE)]
        random_layer = kappa == 0.0
        contrast = float(np.median(lr["contrast"]))
        chp = float(np.median(lr["contrast_hp"]))
        results[f"E14_{mu:.0f}_{kappa:g}_contrast"] = {"contrast": lr["contrast"], "contrast_hp": lr["contrast_hp"]}
        print(f" {name}: contrast {contrast:.4f}, high-pass {chp:.4f} [{min(lr['contrast_hp']):.4f},"
              f" {max(lr['contrast_hp']):.4f}]; at sigma {E14_BASE}: B n {np.mean(base['b_count']):.0f}")
        for kind, sig in E14_CASES:
            r = rs[(kind, sig)]
            results[f"E14_{mu:.0f}_{kappa:g}_{kind}_{sig}"] = dict(r, _label=f"{name}, {kind} noise sigma {sig}")
            bc = np.asarray([p["band_common"] for p in r["_probe"]])
            ch = ("  ".join(f"{m} {_paired_text(r['_err'][m], base['_err'][m], in20=True)}"
                            for m in BANDING_METHODS) if (kind, sig) != ("white", E14_BASE) else
                  "(baseline)".ljust(110))
            print(f"  {kind:<5} sigma {sig:6.4f} CNR {chp / sig:5.2f} | {ch} | B n"
                  f" {np.mean(r['b_count']):4.0f} | bc {100 * np.mean(bc >= BAND_COMMON_MIN):3.0f} %"
                  f" row_min {min(p['row_min'] for p in r['_probe']):.2f}")
        lims = {}
        for m in BANDING_METHODS:
            for kind in ("white", "corr"):
                for frac, lab in ((0.5, "good"), (1.0, "poor")):
                    lim = _e14_limit(rs, base, m, kind, frac, random_layer)
                    lim["cnr"] = chp / lim["sigma"]
                    lims[f"{m}_{kind}_{lab}"] = lim
                    w = worst.get((m, kind, lab))
                    if w is None or lim["cnr"] > w[0]:
                        worst[(m, kind, lab)] = (lim["cnr"], name, lim)
        summary[name] = dict(lims, contrast=contrast, contrast_hp=chp)
        for m in BANDING_METHODS:
            print(f"  limits {m:<8} " + " | ".join(
                f"{kind}: Good {_e14_limit_text(lims[f'{m}_{kind}_good'], chp)}, Poor"
                f" {_e14_limit_text(lims[f'{m}_{kind}_poor'], chp)}" for kind in ("white", "corr")))
    results["E14_summary"] = summary
    results["E14_worst"] = {f"{m}_{kind}_{lab}": {"cnr": v[0], "layer": v[1], **v[2]}
                            for (m, kind, lab), v in worst.items()}
    print(" Most conservative limits across layers (largest CNR; the random layer counts for spread and in20 only): "
          + "  ".join(f"{m} white Good {_e14_worst_text(worst[(m, 'white', 'good')])} Poor"
                      f" {_e14_worst_text(worst[(m, 'white', 'poor')])}, corr Good"
                      f" {_e14_worst_text(worst[(m, 'corr', 'good')])} Poor {_e14_worst_text(worst[(m, 'corr', 'poor')])}"
                      for m in BANDING_METHODS))
    print("  (deciding layer: " + "; ".join(
        f"{m} {kind} {lab} {worst[(m, kind, lab)][1]}" for m in BANDING_METHODS for kind in ("white", "corr")
        for lab in ("good", "poor")) + ")")


def _e14_worst_text(w):
    """Most conservative CNR of a limit across layers: (cnr, layer, limit) -> text with the "<=" and "*" marks."""
    return f"{'<=' if w[2]['exit'] is None else ''}{w[0]:.1f}{'*' if w[2]['fragile'] else ''}"


if __name__ == "__main__":
    sys.exit(main())
