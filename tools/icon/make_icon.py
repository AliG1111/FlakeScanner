#!/usr/bin/env python3
"""Draw the Flake Scanner app icon: light wood strands, mostly aligned, on dark slate, with a thin accent arrow
for the machine direction (MD).

Deterministic (fixed seed, no clock). Needs numpy and OpenCV. Run from the repository root:

    python3 -I tools/icon/make_icon.py

Writes FlakeScanner/Assets.xcassets/AppIcon.appiconset/AppIcon.png: 1024 x 1024, 3-channel RGB, no alpha
(the App Store rejects icons with an alpha channel).
"""
import math
import os
import random

import cv2
import numpy as np

SIZE = 1024
SEED = 20261123
SLATE_TOP = (52, 66, 78)       # RGB, background gradient
SLATE_BOTTOM = (28, 36, 44)
ACCENT = (255, 150, 50)        # RGB, MD arrow
WOOD = [(236, 214, 170), (226, 196, 148), (216, 182, 134), (240, 224, 188), (222, 200, 160)]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "FlakeScanner", "Assets.xcassets",
                   "AppIcon.appiconset", "AppIcon.png")


def background():
    t = np.linspace(0.0, 1.0, SIZE, dtype=np.float32)[:, None, None]
    top = np.array(SLATE_TOP, np.float32)[None, None, :]
    bottom = np.array(SLATE_BOTTOM, np.float32)[None, None, :]
    column = top * (1.0 - t) + bottom * t
    return np.repeat(column, SIZE, axis=1)  # (SIZE, SIZE, 3) float, RGB


def rect_points(cx, cy, length, width, angle_deg):
    a = math.radians(angle_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    hl, hw = length / 2.0, width / 2.0
    corners = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]
    return np.array([[cx + ux * x + vx * y, cy + uy * x + vy * y] for x, y in corners], np.float64)


def fill_poly(img, pts, color):
    shift = 4
    scaled = np.round(pts * (1 << shift)).astype(np.int32)
    cv2.fillConvexPoly(img, scaled, color, lineType=cv2.LINE_AA, shift=shift)


def main():
    rng = random.Random(SEED)
    img = background()
    img = np.clip(img, 0, 255).astype(np.uint8)  # RGB; converted to BGR at the end

    # Strands: six rows around a clear lane at y = 512 for the arrow; angles scatter a few degrees about 0.
    rows = [190, 295, 400, 624, 729, 834]
    for y in rows:
        x = 120.0 + rng.uniform(0.0, 50.0)
        while x < 880.0:
            length = rng.uniform(150.0, 270.0)
            width = rng.uniform(40.0, 56.0)
            angle = max(-14.0, min(14.0, rng.gauss(0.0, 6.0)))
            cx = x + length / 2.0
            cy = y + rng.uniform(-14.0, 14.0)
            if cx + length / 2.0 < 912.0:
                base = rng.choice(WOOD)
                shade = rng.uniform(0.92, 1.0)
                color = tuple(int(round(c * shade)) for c in base)
                pts = rect_points(cx, cy, length, width, angle)
                # Dark rim first (slightly larger) so neighbouring strands stay separate.
                fill_poly(img, rect_points(cx, cy, length + 6.0, width + 6.0, angle), (22, 28, 34))
                fill_poly(img, pts, color)
            x += length + rng.uniform(14.0, 30.0)

    # MD arrow along the lane: a thin line with a head, drawn over a dark halo for contrast.
    y0 = 512
    x_start, x_end = 170, 854
    head = 54
    for thickness, color in ((26, (22, 28, 34)), (12, ACCENT)):
        cv2.line(img, (x_start, y0), (x_end - head // 2, y0), color, thickness, cv2.LINE_AA)
    for grow, color in ((10, (22, 28, 34)), (0, ACCENT)):
        tip = np.array([x_end + grow, y0], np.float64)
        wing = np.array([[x_end - head - grow * 0.5, y0 - head * 0.62 - grow],
                         [x_end - head - grow * 0.5, y0 + head * 0.62 + grow]], np.float64)
        fill_poly(img, np.vstack([tip, wing]), color)

    out = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    assert out.shape == (SIZE, SIZE, 3) and out.dtype == np.uint8
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    if not cv2.imwrite(OUT, out):
        raise SystemExit("could not write " + OUT)


if __name__ == "__main__":
    main()
