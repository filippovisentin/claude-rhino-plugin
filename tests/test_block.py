"""Block: a whole building with a facade on each side (pure Python)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import SpecError, check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402
from rhinospec.naming import layer_path  # noqa: E402

BLOCK = {"type": "block", "name": "angolo", "w": 20, "d": 12, "h": 15, "floors": 5, "roof": "flat", "faces": {
    "front": {"px": [0, 0, 400, 300], "els": [
        {"k": "window", "box": [40, 40, 80, 90], "grid": [5, 4, 70, 60]},
        {"k": "door", "box": [154, 250, 176, 300]}]},
    "right": {"els": [{"k": "window", "box": [2, 2, 1.2, 1.6], "grid": [4, 4, 2.5, 3]}]},
}}


def parts(block=None, units="m", lang="en"):
    return validate({"units": units, "lang": lang, "layer": "T", "parts": [block or BLOCK]})["parts"]


def walls(ps):
    return dict((p["face"], p) for p in ps if p.get("cat") == "walls")


def union(boxes):
    return [min(b[i] for b in boxes) for i in range(3)] + [max(b[i] for b in boxes) for i in range(3, 6)]


def close(a, b, tol=1e-6):
    return all(abs(x - y) < tol for x, y in zip(a, b))


class Block(unittest.TestCase):
    def test_layers_per_face(self):
        paths = set("::".join(layer_path("T", p, "it")) for p in parts(lang="it"))
        self.assertIn("T::angolo::Fronte::Finestre::Vetri", paths)
        self.assertIn("T::angolo::Fronte::Porte::Ante", paths)
        self.assertIn("T::angolo::Destra::Finestre::Telai", paths)
        self.assertIn("T::angolo::Retro::Muri", paths)
        self.assertIn("T::angolo::Sinistra::Muri", paths)
        self.assertIn("T::angolo::Solai", paths)
        self.assertIn("T::angolo::Tetto", paths)

    def test_walls_close_the_footprint(self):
        w = walls(parts())
        self.assertEqual(len(w), 4)
        expect = {"front": [0, 0, 0, 20, 0.4, 15], "back": [0, 11.6, 0, 20, 12, 15],
                  "right": [19.6, 0, 0, 20, 12, 15], "left": [0, 0, 0, 0.4, 12, 15]}
        for key, want in expect.items():
            self.assertTrue(close(bbox(w[key]), want), (key, bbox(w[key])))

    def test_side_walls_give_up_their_corners(self):
        w = walls(parts())
        for key in ("right", "left"):
            cuts = [bbox(c) for c in w[key]["cut"]]
            self.assertEqual(len(cuts), 2)
            ys = sorted((round(c[1], 3), round(c[4], 3)) for c in cuts)
            self.assertEqual(ys, [(-0.001, 0.4), (11.6, 12.001)], key)
        for key in ("front", "back"):   # only the door's edge cut, no corner boxes
            self.assertFalse([c for c in w[key].get("cut", []) if c["type"] == "box"], key)

    def test_openings_land_on_their_face(self):
        ps = parts()
        glass = [bbox(p) for p in ps if p.get("cat") == "windows/glass" and p["face"] == "right"]
        self.assertEqual(len(glass), 16)
        for b in glass:   # recessed into the right wall, x between 19.6 and 20
            self.assertTrue(19.6 - 1e-9 <= b[0] and b[3] <= 20 + 1e-9, b)
        door = [bbox(p) for p in ps if p.get("cat") == "doors/leaves"]
        self.assertEqual(len(door), 1)
        self.assertAlmostEqual(door[0][2], 0.06)   # door box starts on the ground line, inside the frame

    def test_rotation_and_position(self):
        b = dict(BLOCK, rot=90, at=[100, 50, 3])
        u = union([bbox(p) for p in parts(b)])
        self.assertTrue(close(u, [88, 50, 3, 100, 70, 18.3]), u)

    def test_floors_and_gable(self):
        ps = parts(dict(BLOCK, roof="gable", roof_h=4))
        floors = [p for p in ps if p.get("cat") == "floors"]
        self.assertEqual(len(floors), 4)
        roof = [bbox(p) for p in ps if p.get("cat") == "roof"]
        self.assertTrue(close(union(roof), [0, 0, 15, 20, 12, 19.3]), union(roof))
        deep = dict(BLOCK, w=8, d=14, roof="gable", roof_h=4)
        roof = [bbox(p) for p in parts(deep) if p.get("cat") == "roof"]
        self.assertTrue(close(union(roof), [0, 0, 15, 8, 14, 19.3]), union(roof))

    def test_plain_block_and_units(self):
        plain = {"type": "block", "w": 6000, "d": 4000, "h": 3000}
        ps = parts(plain, units="mm")
        w = walls(ps)
        self.assertTrue(close(bbox(w["front"]), [0, 0, 0, 6000, 400, 3000]))
        self.assertTrue(close(union([bbox(p) for p in ps]), [0, 0, 0, 6000, 4000, 3300]))

    def test_builds_with_no_floating_parts(self):
        out = check({"units": "m", "parts": [BLOCK]})
        self.assertIn('"ok": true', out)
        self.assertNotIn("floating", out)

    def test_rejects(self):
        bad = [
            (dict(BLOCK, faces={"top": {"els": [{"k": "window", "box": [1, 1, 1, 1]}]}}), "faces.top"),
            (dict(BLOCK, faces={"front": {"w": 3, "els": [{"k": "window", "box": [1, 1, 1, 1]}]}}), "faces.front"),
            (dict(BLOCK, faces={"front": {"els": []}}), "faces.front.els"),
            (dict(BLOCK, faces=[1]), ".faces"),
            (dict(BLOCK, t=7), ".w"),
            (dict(BLOCK, t=0.01), ".t"),
            (dict(BLOCK, roof="dome"), ".roof"),
            (dict(BLOCK, depth=3), "unknown key(s) depth"),
        ]
        for spec, where in bad:
            with self.assertRaises(SpecError) as cm:
                parts(spec)
            self.assertIn(where, str(cm.exception), spec)


if __name__ == "__main__":
    unittest.main()
