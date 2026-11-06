"""Straightens a facade photographed at an angle, so it can be read like an elevation.

  node "<plugin>/scripts/run-tool.mjs" rectify IMAGE "x,y x,y x,y x,y" OUT [--ratio W/H] [--size 768]

The four points are the facade corners in IMAGE pixels: top-left, top-right, bottom-right,
bottom-left. OUT shows only the facade, straightened, long side --size pixels. --ratio is the
real width/height of the facade when known (e.g. 18/14); otherwise it is estimated from the
corner distances, which is close for moderate angles. Then read OUT with a facade spec whose
px is [0, 0, OUT width, OUT height].

Prints one line: {"out": path, "size": [w, h], "ratio": r}. Needs numpy and Pillow.
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image


def homography(src, dst):
    """3x3 H with H @ [x, y, 1] ~ dst for each of four point pairs (direct linear solve)."""
    a, b = [], []
    for (x, y), (u, v) in zip(src, dst):
        a.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        a.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        b += [u, v]
    h = np.linalg.solve(np.array(a, dtype=float), np.array(b, dtype=float))
    return np.append(h, 1.0).reshape(3, 3)


def parse_corners(text):
    pts = [tuple(float(v) for v in p.split(",")) for p in text.split()]
    if len(pts) != 4 or any(len(p) != 2 for p in pts):
        raise ValueError("expected four x,y corners: top-left top-right bottom-right bottom-left")
    return pts


def estimate_ratio(c):
    """Width/height from the mean opposite-edge lengths (good for moderate perspective)."""
    d = lambda p, q: math.hypot(p[0] - q[0], p[1] - q[1])
    w = (d(c[0], c[1]) + d(c[3], c[2])) / 2.0
    h = (d(c[0], c[3]) + d(c[1], c[2])) / 2.0
    return w / h


def check_convex(c):
    """The corners must form a convex quad in the stated order (clockwise on screen)."""
    signs = []
    for i in range(4):
        (x0, y0), (x1, y1), (x2, y2) = c[i], c[(i + 1) % 4], c[(i + 2) % 4]
        signs.append((x1 - x0) * (y2 - y1) - (y1 - y0) * (x2 - x1))
    if not (all(s > 0 for s in signs) or all(s < 0 for s in signs)):
        raise ValueError("corners do not form a convex quadrilateral in TL, TR, BR, BL order")


def rectify(img, corners, ratio=None, size=768):
    check_convex(corners)
    r = ratio or estimate_ratio(corners)
    if not (0.05 < r < 20):
        raise ValueError("implausible width/height ratio %.3f" % r)
    w, h = (size, max(1, int(round(size / r)))) if r >= 1 else (max(1, int(round(size * r))), size)
    out_corners = [(0, 0), (w, 0), (w, h), (0, h)]
    # PIL wants the map from output pixels to input pixels.
    H = homography(out_corners, corners)
    coeffs = (H / H[2, 2]).flatten()[:8]
    warped = img.convert("RGB").transform((w, h), Image.PERSPECTIVE, tuple(coeffs), Image.BICUBIC)
    return warped, r


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    src, corners, dst = argv[1], parse_corners(argv[2]), argv[3]
    ratio, size, i = None, 768, 4
    while i < len(argv):
        if argv[i] == "--ratio":
            num, _, den = argv[i + 1].partition("/")
            ratio = float(num) / float(den or 1)
            i += 2
        elif argv[i] == "--size":
            size = max(64, min(2048, int(argv[i + 1])))
            i += 2
        else:
            raise SystemExit("unknown option %r" % argv[i])
    with Image.open(src) as im:
        out, r = rectify(im, corners, ratio, size)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    out.save(dst, quality=90)
    print(json.dumps({"out": dst, "size": list(out.size), "ratio": round(r, 3)}))


if __name__ == "__main__":
    main(sys.argv)
