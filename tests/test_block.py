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


def connected_groups(ps, tol=1e-3):
    """How many separate clusters of touching parts (a building should be one): checks.floating
    only flags parts that touch nothing, so a roof whose two tiers touch each other but not the
    walls slips through it."""
    boxes = [bbox(p) for p in ps]
    group = list(range(len(boxes)))

    def root(i):
        while group[i] != i:
            group[i] = group[group[i]]
            i = group[i]
        return i

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if all(boxes[i][k] <= boxes[j][k + 3] + tol and boxes[j][k] <= boxes[i][k + 3] + tol for k in range(3)):
                group[root(i)] = root(j)
    return len(set(root(i) for i in range(len(boxes))))


class Block(unittest.TestCase):
    def test_layers_per_face(self):
        paths = set("::".join(layer_path("T", p, "it")) for p in parts(lang="it"))
        self.assertIn("T::angolo::Fronte::Finestre::Vetri", paths)
        self.assertIn("T::angolo::Fronte::Porte::Ante", paths)
        self.assertIn("T::angolo::Destra::Finestre::Telai", paths)
        self.assertIn("T::angolo::Retro::Muri", paths)
        self.assertIn("T::angolo::Sinistra::Muri", paths)
        self.assertIn("T::angolo::Solai", paths)
        self.assertIn("T::angolo::Tetto::Copertura piana", paths)   # BLOCK has a flat roof

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
        self.assertEqual(len(door), 3)                      # one leaf with two raised panels
        self.assertAlmostEqual(min(b[2] for b in door), 0.06)   # starts on the ground line, inside the frame

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

    def test_style_reaches_every_face(self):
        ps = parts(dict(BLOCK, style="classic"))
        self.assertTrue([p for p in ps if p.get("face") == "front" and p.get("cat") == "windows/surrounds"])
        self.assertTrue([p for p in ps if p.get("face") == "right" and p.get("cat") == "windows/surrounds"])
        self.assertFalse([p for p in parts() if p.get("cat") == "windows/surrounds"])

    def test_hip_and_mansard_roofs(self):
        for roof, tiers in (("hip", 1), ("mansard", 2)):
            ps = parts(dict(BLOCK, roof=roof, roof_h=5))
            lofts = [p for p in ps if p["type"] == "loft"]
            self.assertEqual(len(lofts), tiers, roof)
            u = union([bbox(p) for p in lofts])
            self.assertTrue(close(u, [0, 0, 15.3, 20, 12, 20.3]), (roof, u))
        square = dict(BLOCK, w=10, d=10, roof="hip")   # a pyramid still has a (tiny) ridge
        self.assertEqual(len([p for p in parts(square) if p["type"] == "loft"]), 1)

    def test_dormers(self):
        ps = parts(dict(BLOCK, roof="mansard", roof_h=5, dormers=5))
        bodies = [p for p in ps if p.get("cat") == "roof/dormers" and p["type"] == "box"]
        glass = [p for p in ps if p.get("cat") == "roof/dormers/glass"]
        self.assertEqual((len(bodies), len(glass)), (10, 10))      # five on the front, five on the back
        for p in bodies:   # inside the roof outline, above the walls
            b = bbox(p)
            self.assertTrue(0 < b[0] and b[3] < 20 and 0 < b[1] and b[4] < 12 and b[2] > 15.3 and b[5] < 20.3, b)
        paths = set("::".join(layer_path("T", p, "it")) for p in ps)
        self.assertIn("T::angolo::Tetto::Abbaini::Vetri", paths)
        # gable and hip: only on slopes facing front and back (w >= d); never on flat roofs or low pitches
        self.assertTrue([p for p in parts(dict(BLOCK, roof="gable", roof_h=4, dormers=3)) if p.get("cat") == "roof/dormers"])
        self.assertFalse([p for p in parts(dict(BLOCK, roof="flat", dormers=3)) if "dormer" in p["name"]])
        self.assertFalse([p for p in parts(dict(BLOCK, roof="hip", roof_h=1, dormers=3)) if "dormer" in p["name"]])
        self.assertFalse([p for p in parts(dict(BLOCK, w=8, d=14, roof="gable", roof_h=4, dormers=3))
                          if "dormer" in p["name"]])

    def test_chimneys(self):
        ps = parts(dict(BLOCK, roof="gable", roof_h=4, chimneys=2))
        stacks = [bbox(p) for p in ps if p.get("cat") == "roof/chimneys" and "cap" not in p["name"]]
        self.assertEqual(len(stacks), 2)
        for b in stacks:   # on the ridge, a metre above it
            self.assertAlmostEqual(b[1], 5.7)
            self.assertAlmostEqual(b[5], 15.3 + 4 + 1)
        self.assertFalse([p for p in parts(dict(BLOCK, roof="none", chimneys=2)) if "chimney" in p["name"]])

    def test_plain_block_and_units(self):
        plain = {"type": "block", "w": 6000, "d": 4000, "h": 3000}
        ps = parts(plain, units="mm")
        w = walls(ps)
        self.assertTrue(close(bbox(w["front"]), [0, 0, 0, 6000, 400, 3000]))
        self.assertTrue(close(union([bbox(p) for p in ps]), [0, 0, 0, 6000, 4000, 3300]))

    def test_a_face_without_elements_is_a_plain_wall(self):
        # els:[] (or an empty face) is how readers write a blind side: same as leaving the face out
        blind = dict(BLOCK, faces=dict(BLOCK["faces"], back={"els": []}, left={}))
        self.assertEqual(len(parts(blind)), len(parts(BLOCK)))

    def test_builds_with_no_floating_parts(self):
        out = check({"units": "m", "parts": [BLOCK]})
        self.assertIn('"ok": true', out)
        self.assertNotIn("floating", out)

    def test_floor_slabs_never_cross_a_window(self):
        # Window rows 2.6-4.2, 5.6-7.2, 8.6-10.2, 11.6-13.2 on the front and a door on the right:
        # the evenly spaced slabs (tops at 3, 6, 9, 12) would show through the glass.
        b = dict(BLOCK, faces={"front": {"els": [{"k": "window", "box": [1, 2.6, 1.2, 1.6], "grid": [5, 4, 3.5, 3]}]},
                               "right": {"els": [{"k": "door", "box": [4, 0, 1.2, 2.4]}]}})
        for spec_part in (b, dict(b, type="facade", w=20, h=15, depth=12, els=b["faces"]["front"]["els"])):
            if spec_part["type"] == "facade":
                spec_part = {k: v for k, v in spec_part.items() if k not in ("faces", "d")}
            ps = parts(spec_part)
            slabs = sorted(bbox(p) for p in ps if p.get("cat") == "floors")
            self.assertEqual(len(slabs), 4, spec_part["type"])
            glass = [bbox(p) for p in ps if p.get("cat", "").endswith("/glass")]
            for s in slabs:
                for g in glass:
                    self.assertFalse(min(s[5], g[5]) - max(s[2], g[2]) > 1e-6, (spec_part["type"], s, g))
            tops = [s[5] for s in slabs]
            self.assertEqual(tops, sorted(tops))
            for k, t in enumerate(tops, 1):           # still near their storey
                self.assertLess(abs(t - 3 * k), 1.5 + 1e-9, (spec_part["type"], tops))
        # A double-height opening no slab can avoid: the slab is cut back behind it (a double-height
        # space), 1.5 m deep and as wide as the opening, and stays whole elsewhere.
        tall = [{"k": "shop", "box": [2, 0.5, 4, 6.5], "shape": "arch"}]
        for spec_part in (dict(BLOCK, floors=5, faces={"front": {"els": tall}}),
                          {"type": "facade", "name": "angolo", "w": 20, "h": 15, "floors": 5, "depth": 12, "els": tall}):
            ps = parts(spec_part)
            crossing = [p for p in ps if p.get("cat") == "floors" and bbox(p)[2] < 7.0 and bbox(p)[5] > 0.5]
            self.assertTrue(crossing, spec_part["type"])
            for slab in crossing:
                self.assertTrue(slab.get("cut"), spec_part["type"])
                c = bbox(slab["cut"][0])
                self.assertTrue(c[0] <= 2 and c[3] >= 6, c)             # the opening's width
                self.assertTrue(c[1] <= 0.4 and c[4] >= 1.5, c)         # from the wall 1.5 m in
                self.assertTrue(c[2] < bbox(slab)[2] and c[5] > bbox(slab)[5], c)
            self.assertFalse([p for p in ps if p.get("cat") == "floors" and bbox(p)[2] >= 7.0 and p.get("cut")])
        # Slabs already clear of the openings stay where they were.
        clear = dict(BLOCK, faces={"front": {"els": [{"k": "window", "box": [1, 1, 1.2, 1.4], "grid": [5, 5, 3.5, 3]}]}})
        tops = sorted(bbox(p)[5] for p in parts(clear) if p.get("cat") == "floors")
        for got, want in zip(tops, [3, 6, 9, 12]):
            self.assertAlmostEqual(got, want)

    def test_flat_roof_has_its_own_colour(self):
        # A flat roof is not a tiled one: its slab gets its own layer and a neutral colour, the
        # palette's roof colour still wins; under a pitched roof the slab stays with the roof.
        for part in (dict(BLOCK, roof="flat"),
                     {"type": "facade", "name": "angolo", "w": 20, "h": 15, "depth": 12, "roof": "flat",
                      "els": [{"k": "window", "box": [1, 1, 1, 1]}]}):
            ps = parts(part, lang="it")
            slab = [p for p in ps if p["name"].endswith("roof slab")][0]
            self.assertEqual(slab["cat"], "roof/flat", part["type"])
            self.assertEqual(layer_path("T", slab, "it")[-2:], ["Tetto", "Copertura piana"])
            painted = [p for p in parts(dict(part, palette={"roof": "#445566"})) if p["name"].endswith("roof slab")][0]
            self.assertEqual(painted["color"], "#445566")
        pitched = [p for p in parts(dict(BLOCK, roof="gable", roof_h=4)) if p["name"].endswith("roof slab")][0]
        self.assertEqual(pitched["cat"], "roof")

    def test_every_roof_rests_on_a_slab(self):
        # The roof (and the dormers and chimneys planned with it) starts 30 cm above the walls:
        # a slab must fill that gap for every pitched roof, not only flat and gable ones.
        for roof in ("flat", "gable", "hip", "mansard"):
            b = dict(BLOCK, roof=roof, roof_h=5, dormers=3, chimneys=2)
            ps = parts(b)
            slabs = [bbox(p) for p in ps if p["name"].endswith("roof slab")]
            self.assertEqual(len(slabs), 1, roof)
            self.assertTrue(close(slabs[0], [0, 0, 15, 20, 12, 15.3]), (roof, slabs[0]))
            self.assertEqual(connected_groups(ps), 1, roof)
            self.assertNotIn("floating", check({"units": "m", "parts": [b]}), roof)
        self.assertFalse([p for p in parts(dict(BLOCK, roof="none")) if "roof" in p["name"]])

    def test_rejects(self):
        bad = [
            (dict(BLOCK, faces={"top": {"els": [{"k": "window", "box": [1, 1, 1, 1]}]}}), "faces.top"),
            (dict(BLOCK, faces={"front": {"w": 3, "els": [{"k": "window", "box": [1, 1, 1, 1]}]}}), "faces.front"),
            (dict(BLOCK, faces={"front": {"els": "none"}}), "faces.front.els"),
            (dict(BLOCK, faces=[1]), ".faces"),
            (dict(BLOCK, t=7), ".w"),
            (dict(BLOCK, t=0.01), ".t"),
            (dict(BLOCK, roof="dome"), ".roof"),
            (dict(BLOCK, style="gothic"), ".style"),
            (dict(BLOCK, depth=3), "unknown key(s) depth"),
        ]
        for spec, where in bad:
            with self.assertRaises(SpecError) as cm:
                parts(spec)
            self.assertIn(where, str(cm.exception), spec)


if __name__ == "__main__":
    unittest.main()
