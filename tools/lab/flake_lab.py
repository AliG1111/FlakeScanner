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

Usage:
  python3 -I tools/lab/flake_lab.py            # all experiments, prints tables
  python3 -I tools/lab/flake_lab.py --quick    # fewer images per condition
  python3 -I tools/lab/flake_lab.py --only E9  # selected experiments (repeatable)
  python3 -I tools/lab/flake_lab.py --save-example out.png

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


def render_mat(rng, size=768, n=650, mu=0.0, kappa=4.0, length=120.0, width=24.0,
               grain=0.06, noise=0.012, psf=0.7, motion_blur=0.0, banding=0.0,
               band_period=40.0, shadow=None):
    """Render a mat of `n` strands; returns (8-bit image, truth dict).

    length/width are mean strand dimensions in output pixels (each strand +-30 %).
    motion_blur: box blur length in px along +x (MD) after optics.
    banding: relative amplitude of a row-wise (sensor readout) sinusoid, e.g. 0.1.
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
    if banding > 0:
        rows = np.arange(size, dtype=np.float32)[:, None]
        img = img * (1.0 + banding * np.sin(2.0 * math.pi * rows / band_period))
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


def structure_tensor(img8, sigma_d=1.0, sigma_i=6.0, row_normalize=False):
    img = img8.astype(np.float32) / 255.0
    if row_normalize:                               # divide out row-wise (banding) gain
        rm = img.mean(axis=1, keepdims=True)
        img = img / np.maximum(rm, 1e-3) * float(rm.mean())
    g, d = _gauss_kernels(sigma_d)
    # sepFilter2D correlates; derivative sign is consistent for x and y, so Jxy keeps its sign.
    gx = cv2.sepFilter2D(img, cv2.CV_32F, d, g, borderType=cv2.BORDER_REFLECT)
    gy = cv2.sepFilter2D(img, cv2.CV_32F, g, d, borderType=cv2.BORDER_REFLECT)
    jxx = cv2.GaussianBlur(gx * gx, (0, 0), sigma_i)
    jyy = cv2.GaussianBlur(gy * gy, (0, 0), sigma_i)
    jxy = cv2.GaussianBlur(gx * gy, (0, 0), sigma_i)
    return jxx, jyy, jxy


def estimate_tensor(img8, sigma_d=1.0, sigma_i=6.0, coh_min=0.0, weight="energy*coh",
                    border=None, row_normalize=False):
    jxx, jyy, jxy = structure_tensor(img8, sigma_d, sigma_i, row_normalize)
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


def row_normalize8(img8):
    """Divide each row by its mean (removes row-wise gain such as flicker banding); returns 8-bit."""
    img = img8.astype(np.float32)
    rm = img.mean(axis=1, keepdims=True)
    out = img / np.maximum(rm, 1.0) * float(rm.mean())
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


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


# ----------------------------------------------------------------------------------------------
# Experiments
# ----------------------------------------------------------------------------------------------

def run_condition(seed, images, **mat):
    """Pool estimates over `images` mats; returns per-method stats and truth."""
    rng = np.random.default_rng(seed)
    pools = {"truth": ([], None), "A_tensor": ([], []), "A_tensor_coh": ([], []),
             "B_seg_count": ([], None), "B_seg_len": ([], []), "B_merged": ([], None)}
    row_norm = mat.pop("row_normalize", False)
    timing = {"A": 0.0, "B": 0.0}
    for _ in range(images):
        img, truth = render_mat(rng, **mat)
        if row_norm:
            img = row_normalize8(img)
        vis = truth["visible_frac"] >= 0.25
        pools["truth"][0].append(truth["theta"][vis])
        t0 = time.perf_counter()
        th, w = estimate_tensor(img, sigma_i=0.25 * mat.get("width", 24.0))
        pools["A_tensor"][0].append(th)
        pools["A_tensor"][1].append(w)
        th2, w2 = estimate_tensor(img, sigma_i=0.25 * mat.get("width", 24.0), coh_min=0.5, weight="coh")
        pools["A_tensor_coh"][0].append(th2)
        pools["A_tensor_coh"][1].append(w2)
        timing["A"] += time.perf_counter() - t0
        t0 = time.perf_counter()
        ths, ln = estimate_segments(img, min_len=1.5 * mat.get("width", 24.0))
        timing["B"] += time.perf_counter() - t0
        pools["B_seg_count"][0].append(ths)
        pools["B_seg_len"][0].append(ths)
        pools["B_seg_len"][1].append(ln)
        thm, _ = estimate_segments_merged(img, min_len=1.5 * mat.get("width", 24.0),
                                          max_gap=2.0 * mat.get("width", 24.0))
        pools["B_merged"][0].append(thm)
    out = {}
    for k, (ths, ws) in pools.items():
        th = np.concatenate(ths)
        w = None if ws is None else np.concatenate(ws)
        out[k] = axial_stats(th, w)
    out["_timing_ms"] = {k: 1000.0 * v / images for k, v in timing.items()}
    return out


def fmt_row(name, s, truth=None):
    if s.get("n", 0) == 0:
        return f"  {name:<14} n=0"
    t = ""
    if truth is not None:
        t = (f"  | err mean {axial_diff(s['mean'], truth['mean']):+6.2f}  sd {s['sd'] - truth['sd']:+6.2f}"
             f"  in20 {s['in20'] - truth['in20']:+6.1f}  f {s['f'] - truth['f']:+.3f}")
    return (f"  {name:<14} n={s['n']:>7}  mean {s['mean']:+7.2f}  sd {s['sd']:6.2f}  R {s['R']:.3f}"
            f"  f {s['f']:+.3f}  in20 {s['in20']:5.1f}%  mad {s['mad']:5.2f}{t}")


METHODS = ("A_tensor", "A_tensor_coh", "B_seg_count", "B_seg_len", "B_merged")


def report(title, res):
    print(title)
    tr = res["truth"]
    print(fmt_row("truth", tr))
    for m in METHODS:
        print(fmt_row(m, res[m], tr))
    print(f"  time per 768x768 image (Python/OpenCV, this PC): A {res['_timing_ms']['A']:.0f} ms,"
          f" B {res['_timing_ms']['B']:.0f} ms")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true", help="2 images per condition instead of 4")
    ap.add_argument("--save-example", metavar="PNG", help="write one synthetic mat and exit")
    ap.add_argument("--json", metavar="FILE", help="also write all results as JSON")
    ap.add_argument("--only", metavar="E", action="append",
                    help="run only these experiments (E1..E9); repeatable")
    args = ap.parse_args(argv)
    images = 2 if args.quick else 4

    if args.save_example:
        img, _ = render_mat(np.random.default_rng(1), mu=10.0, kappa=4.0)
        cv2.imwrite(args.save_example, img)
        return 0

    results = {}
    want = (lambda e: True) if not args.only else (lambda e: e in args.only)
    if want("E1"):
        experiment_e1(images, results)
    if want("E2"):
        experiment_e2(images, results)
    if want("E3"):
        experiment_e3(images, results)
    if want("E4"):
        experiment_e4(images, results)
    if want("E5"):
        experiment_e5(images, results)
    if want("E6"):
        experiment_e6(images, results)
    if want("E7"):
        experiment_e7(images, results)
    if want("E8"):
        experiment_e8(images, results)
    if want("E9"):
        experiment_e9(images, results)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, default=float)
    return 0


def experiment_e1(images, results):
    print("E1  Mean-angle bias vs true mean direction (kappa 4, aspect 5:1)")
    for mu in (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0):
        r = run_condition(100 + int(mu), images, mu=mu, kappa=4.0)
        results[f"E1_mu{int(mu)}"] = r
        tr = r["truth"]
        errs = "  ".join(f"{m} {axial_diff(r[m]['mean'], tr['mean']):+5.2f}" for m in METHODS)
        print(f"  mu {mu:4.0f}: truth mean {tr['mean']:+6.2f}  errors: {errs}")


def experiment_e2(images, results):
    print("\nE2  Spread vs concentration (mu 0)")
    for kappa in (0.0, 1.0, 2.0, 4.0, 8.0):
        r = run_condition(200 + int(kappa * 10), images, mu=0.0, kappa=kappa)
        results[f"E2_k{kappa}"] = r
        report(f" kappa {kappa}", r)


def experiment_e3(images, results):
    print("\nE3  Motion blur along MD (mu 10, kappa 4)")
    for mb in (0.0, 2.0, 4.0, 8.0):
        r = run_condition(300, images, mu=10.0, kappa=4.0, motion_blur=mb)
        results[f"E3_blur{int(mb)}"] = r
        report(f" blur {mb:.0f} px", r)


def experiment_e4(images, results):
    print("\nE4  Row banding (flicker + rolling shutter), 10 % amplitude, 40-row period (mu 10, kappa 4)")
    for rn in (False, True):
        r = run_condition(400, images, mu=10.0, kappa=4.0, banding=0.10, row_normalize=rn)
        results[f"E4_band_rownorm{int(rn)}"] = r
        report(f" banding, row normalization {'on' if rn else 'off'}", r)


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


def experiment_e9(images, results):
    print("\nE9  Collinear merging of edge pieces vs mat density (mu 0)")
    for kappa in (2.0, 4.0):
        for n in (650, 1300):
            r = run_condition(900 + n + int(kappa), images, mu=0.0, kappa=kappa, n=n)
            results[f"E9_k{kappa}_n{n}"] = r
            report(f" kappa {kappa}, {n} strands", r)


def experiment_e8(images, results):
    print("\nE8  Rotational bias, paired with the same strands (kappa 16, 3x images)")
    for mu in (0.0, 10.0, 22.5, 30.0, 45.0, 67.5, 80.0, 90.0):
        r = run_condition(800 + int(mu * 10), 3 * images, mu=mu, kappa=16.0)
        results[f"E8_mu{mu}"] = r
        tr = r["truth"]
        errs = "  ".join(f"{m} {axial_diff(r[m]['mean'], tr['mean']):+5.2f}" for m in METHODS)
        print(f"  mu {mu:5.1f}: truth mean {tr['mean']:+6.2f} (n {tr['n']})  errors: {errs}")


if __name__ == "__main__":
    sys.exit(main())
