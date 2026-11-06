"""Camera and sizes from a photo's corners (tools/photo3d.py), on a synthetic photo. Needs numpy."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
try:
    import numpy as np  # noqa: F401
    import photo3d as P
except ImportError:
    P = None


@unittest.skipIf(P is None, "needs numpy")
class Photo3d(unittest.TestCase):
    def setUp(self):
        # a 40 x 20 m block, 60 m high, seen from the front-right and below
        self.cam = {"C": [70.0, -90.0, 2.0], "yaw": math.radians(25), "pitch": math.radians(12),
                    "f": 700.0, "image": [600, 800]}

    def px(self, X):
        return [round(float(c), 2) for c in P.project(self.cam, [X])[0]]

    def test_recovers_sizes_and_camera(self):
        pts = [{"px": self.px([0, 0, 60]), "X": [0, 0, "H"]},
               {"px": self.px([40, 0, 60]), "X": ["W", 0, "H"]},
               {"px": self.px([40, 20, 60]), "X": ["W", "D", "H"]},
               {"px": self.px([0, 0, 0]), "X": [0, 0, 0]},
               {"px": self.px([40, 0, 0]), "X": ["W", 0, 0]},
               {"px": self.px([40, 20, 0]), "X": ["W", "D", 0]},
               {"px": self.px([40, 0, 30]), "X": ["W", 0, "H/2"]}]
        out = P.solve({"image": [600, 800], "known": {"H": 60}, "points": pts,
                       "lines": {"eaves": {"plane": "y=0", "px": [self.px([20, 0, 60])]}}})
        self.assertLess(out["rms"], 0.5)
        self.assertAlmostEqual(out["sizes"]["W"], 40, delta=0.3)
        self.assertAlmostEqual(out["sizes"]["D"], 20, delta=0.3)
        x, z = out["lines"]["eaves"][0]
        self.assertAlmostEqual(x, 20, delta=0.3)
        self.assertAlmostEqual(z, 60, delta=0.3)

    def test_expressions_only_arithmetic(self):
        with self.assertRaises(ValueError):
            P._expr("__import__('os')")
        names, fn = P._expr("Zb+3*F")
        self.assertEqual(sorted(names), ["F", "Zb"])
        self.assertEqual(fn({"Zb": 1.0, "F": 2.0}), 7.0)


if __name__ == "__main__":
    unittest.main()
