"""Silhouette comparison (tools/silhouette.py): projection, rasterising and scoring, no photo or model.
Needs numpy and OpenCV (the detector environment): skipped elsewhere."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
try:
    import numpy as np
    import cv2  # noqa: F401
    import silhouette as S
except ImportError:  # plain Python without numpy/OpenCV
    S = None


def box_mesh(w, d, h, x=0.0):
    v = [[x + a * w, b * d, c * h] for a in (0, 1) for b in (0, 1) for c in (0, 1)]
    q = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    f = [t for a, b, c, e in q for t in ((a, b, c), (a, c, e))]
    return np.array(v, float), np.array(f, np.int32)


@unittest.skipIf(S is None, "needs numpy and OpenCV")
class Silhouette(unittest.TestCase):
    def test_front_view_keeps_proportions(self):
        v, f = box_mesh(20, 10, 40)
        m = S.raster(S.camera(v, 0, 0, 1), f, 200)
        x0, y0, x1, y1 = S.crop(m)
        self.assertAlmostEqual((x1 - x0) / (y1 - y0), 0.5, delta=0.03)

    def test_overlapping_triangles_leave_no_holes(self):
        v1, f1 = box_mesh(20, 10, 40)
        v2, f2 = box_mesh(4, 1, 4, x=8)          # a window box in front of the wall
        v2[:, 1] -= 1
        v = np.vstack([v1, v2])
        f = np.vstack([f1, f2 + len(v1)])
        m = S.raster(S.camera(v, 0, 0, 1), f, 200)
        x0, y0, x1, y1 = S.crop(m)
        self.assertTrue(m[y0 + 2:y1 - 2, x0 + 2:x1 - 2].all())

    def test_same_shape_scores_one(self):
        v, f = box_mesh(20, 10, 40)
        m = S.raster(S.camera(v, 0, 0, 1), f, 120)
        photo = np.zeros((200, 200), bool)
        photo[20:20 + m.shape[0], 50:50 + m.shape[1]] = m
        s, _ = S.score(m, photo)
        self.assertGreater(s["iou"], 0.97)
        self.assertAlmostEqual(s["aspect"], 1.0, delta=0.05)

    def test_bands_show_where_the_model_is_too_narrow(self):
        photo = np.zeros((100, 100), bool)
        photo[10:90, 20:80] = True                # a plain block
        model = np.zeros((80, 60), bool)
        model[:, :] = True
        model[:40, :15] = False                   # model's upper half 25 % narrower
        s, _ = S.score(model, photo)
        self.assertLess(s["bands"][0], 0.9)
        self.assertAlmostEqual(s["bands"][-1], 1.0, delta=0.05)


if __name__ == "__main__":
    unittest.main()
