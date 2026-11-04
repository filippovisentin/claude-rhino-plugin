"""Perspective rectification: warp a synthetic facade, straighten it back, compare."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import rectify as rc  # noqa: E402


def facade_image(w=300, h=200):
    """Wall with a 5x3 grid of dark windows: sharp edges make misalignment visible."""
    a = np.full((h, w), 200, dtype=np.uint8)
    for j in range(3):
        for i in range(5):
            x0, y0 = 20 + i * 56, 20 + j * 60
            a[y0:y0 + 40, x0:x0 + 30] = 40
    return Image.fromarray(a)


def warp(img, corners, canvas=(420, 320)):
    """Places img's rectangle onto the quad corners (TL, TR, BR, BL) of a larger canvas."""
    w, h = img.size
    H = rc.homography(corners, [(0, 0), (w, 0), (w, h), (0, h)])   # canvas -> img
    return img.transform(canvas, Image.PERSPECTIVE, tuple((H / H[2, 2]).flatten()[:8]), Image.BICUBIC,
                         fillcolor=0)


class Rectify(unittest.TestCase):
    corners = [(60, 30), (380, 70), (370, 270), (50, 300)]   # a facade seen from the left, slightly low

    def test_round_trip_restores_the_facade(self):
        src = facade_image()
        out, _ = rc.rectify(warp(src, self.corners), self.corners, ratio=300 / 200.0, size=300)
        self.assertEqual(out.size, (300, 200))
        diff = np.abs(np.asarray(out.convert("L"), float) - np.asarray(src, float))
        self.assertLess(diff.mean(), 6.0)                    # a few grey levels of resampling blur
        self.assertGreater((diff < 30).mean(), 0.97)         # and nearly every pixel lands right

    def test_ratio_estimate_is_close_for_moderate_perspective(self):
        self.assertAlmostEqual(rc.estimate_ratio([(0, 0), (300, 0), (300, 200), (0, 200)]), 1.5)
        est = rc.estimate_ratio(self.corners)
        self.assertLess(abs(est - 1.5) / 1.5, 0.15)

    def test_homography_maps_the_corners(self):
        dst = [(0, 0), (10, 0), (10, 5), (0, 5)]
        H = rc.homography(self.corners, dst)
        for (x, y), (u, v) in zip(self.corners, dst):
            p = H @ np.array([x, y, 1.0])
            self.assertAlmostEqual(p[0] / p[2], u, places=6)
            self.assertAlmostEqual(p[1] / p[2], v, places=6)

    def test_bad_corners_are_rejected(self):
        img = facade_image()
        with self.assertRaises(ValueError):
            rc.rectify(img, [(0, 0), (100, 100), (100, 0), (0, 100)])   # crossed: not convex
        with self.assertRaises(ValueError):
            rc.parse_corners("1,2 3,4 5,6")
        with self.assertRaises(ValueError):
            rc.rectify(img, [(0, 0), (1000, 0), (1000, 1), (0, 1)])     # absurd 1000:1 facade


if __name__ == "__main__":
    unittest.main()
