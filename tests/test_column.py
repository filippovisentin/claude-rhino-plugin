"""Classical column composite (pure Python)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import SpecError, check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402


def parts(col, units="m"):
    return validate({"units": units, "parts": [dict({"type": "column"}, **col)]})["parts"]


def union(ps):
    bs = [bbox(p) for p in ps]
    return [min(b[i] for b in bs) for i in range(3)] + [max(b[i] for b in bs) for i in range(3, 6)]


class Column(unittest.TestCase):
    def test_orders_reach_the_height_and_proportion(self):
        for order, ratio in (("tuscan", 7), ("doric", 8), ("ionic", 9), ("corinthian", 10)):
            ps = parts({"order": order, "h": 4.5})
            u = union(ps)
            d = 4.5 / ratio
            self.assertAlmostEqual(u[2], 0.0)
            self.assertAlmostEqual(u[5], 4.5, places=6)
            self.assertAlmostEqual(u[3] - u[0], 1.35 * d, places=6, msg=order)   # the plinth is widest
            self.assertEqual(set(p["cat"] for p in ps), {"pillars"})
        self.assertEqual(len([p for p in parts({"order": "ionic", "h": 4.5}) if "volute" in p["name"]]), 2)

    def test_colonnade(self):
        ps = parts({"h": 3.5, "d": 0.5, "count": 6, "spacing": 2.0, "at": [10, 0, 0]})
        u = union(ps)
        self.assertAlmostEqual(u[0], 10 - 0.3375)                         # first plinth edge (1.35 d / 2)
        self.assertAlmostEqual(u[3], 10 + 5 * 2.0 + 0.3375)
        self.assertEqual(len([p for p in ps if "shaft" in p["name"]]), 6)
        along_y = union(parts({"h": 3.5, "d": 0.5, "count": 3, "spacing": 2.0, "axis": "y"}))
        self.assertAlmostEqual(along_y[4] - along_y[1], 4.0 + 0.675)

    def test_builds_without_floating_parts(self):
        for order in ("tuscan", "doric", "ionic", "corinthian"):
            out = check({"units": "cm", "parts": [{"type": "column", "order": order, "h": 450, "count": 4}]})
            self.assertIn('"ok": true', out)
            self.assertNotIn("floating", out, order)

    def test_rejects(self):
        for col, where in (({"h": 3, "order": "gothic"}, ".order"), ({"h": 3, "d": 2}, ".d"),
                           ({"h": 3, "count": 3, "spacing": 0.1}, ".spacing"), ({"h": 3, "axis": "z"}, ".axis"),
                           ({"h": 3, "color": "#ff0000"}, "unknown")):
            with self.assertRaises(SpecError) as cm:
                parts(col)
            self.assertIn(where, str(cm.exception))


if __name__ == "__main__":
    unittest.main()
