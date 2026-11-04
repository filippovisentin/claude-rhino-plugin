"""Stair composite: straight and spiral (pure Python)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import SpecError, check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402
from rhinospec.naming import layer_path  # noqa: E402


def parts(stair, units="m"):
    return validate({"units": units, "lang": "it", "parts": [dict({"type": "stair"}, **stair)]})["parts"]


def union(ps):
    bs = [bbox(p) for p in ps]
    return [min(b[i] for b in bs) for i in range(3)] + [max(b[i] for b in bs) for i in range(3, 6)]


class Stair(unittest.TestCase):
    def test_straight_stair_dimensions(self):
        ps = parts({"h": 3.0, "w": 1.1})
        steps = [p for p in ps if p["cat"] == "stairs/steps"]
        self.assertEqual(len(steps), 18)                       # 3.0 / 0.17 -> 18 risers of 0.1667
        u = union(steps)
        for got, want in zip(u, [0, 0, 0, 1.1, 18 * 0.28, 3.0]):
            self.assertAlmostEqual(got, want)
        self.assertEqual(len([p for p in ps if p["type"] == "pipe"]), 2)
        paths = set("::".join(layer_path("L", p, "it")) for p in ps)
        self.assertEqual(paths, {"L::stair::Scale::Gradini", "L::stair::Scale::Ringhiere"})

    def test_rotation_and_rails(self):
        ps = parts({"h": 1.0, "w": 1.0, "rot": 90, "at": [5, 5, 0], "rail": "none"})
        u = union(ps)
        self.assertAlmostEqual(u[3], 5.0)                       # climbs along -x after a 90 degree turn
        self.assertAlmostEqual(u[0], 5 - 6 * 0.28)
        self.assertFalse([p for p in ps if "post" in p["name"]])

    def test_spiral_stair(self):
        ps = parts({"kind": "spiral", "h": 3.0, "r": 1.0, "step": 30})
        steps = [p for p in ps if p["cat"] == "stairs/steps"]
        self.assertEqual(len(steps), 18)
        u = union(ps)
        lim = 1.0 * 2 ** 0.5 + 1e-6      # checks' boxes of rotated wedges are conservative
        self.assertTrue(-lim <= u[0] and u[3] <= lim, u)
        self.assertAlmostEqual(u[5], 3.0 + 0.9 + 0.025, places=3)   # handrail above the last step

    def test_builds_without_floating_parts(self):
        for st in ({"h": 2.8}, {"kind": "spiral", "h": 2.8}, {"h": 2800, "w": 1000}):
            out = check({"units": "mm" if st["h"] > 100 else "m", "parts": [dict({"type": "stair"}, **st)]})
            self.assertIn('"ok": true', out)
            self.assertNotIn("floating", out, st)

    def test_rejects(self):
        for st, where in (({"h": 3, "kind": "ladder"}, ".kind"), ({"h": 3, "rail": "top"}, ".rail"),
                          ({"h": 100}, ".h"), ({"kind": "spiral", "h": 3, "r": 1, "core": 0.9}, ".core"),
                          ({"h": 3, "r": 1}, ".r"), ({"kind": "spiral", "h": 3, "w": 1}, ".w")):
            with self.assertRaises(SpecError) as cm:
                parts(st)
            self.assertIn(where, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
