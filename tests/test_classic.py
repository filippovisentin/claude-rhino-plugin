"""Classic facade detailing: profiles, surrounds, balconies, pilasters, rustication (pure Python)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import SpecError, check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402
from rhinospec.naming import layer_path  # noqa: E402


def parts(els, style="classic", **kw):
    f = dict({"type": "facade", "name": "F", "w": 12, "h": 15, "style": style, "els": els}, **kw)
    return validate({"units": "m", "parts": [f]})["parts"]


def named(ps, word):
    return [p for p in ps if word in p["name"].split()]


class Classic(unittest.TestCase):
    def test_window_surround_shrinks_the_hole(self):
        ps = parts([{"k": "window", "box": [1, 5, 1.4, 2.6], "shape": "arch"}])
        wall = ps[0]
        self.assertEqual(len(wall["holes"]), 1)
        u, v, w, h = wall["holes"][0][:4]
        self.assertAlmostEqual(u, 1.15)
        self.assertAlmostEqual(w, 1.1)
        self.assertAlmostEqual(h, 2.3)
        # two jambs, the sill band and twelve archivolt segments following the arch
        self.assertEqual(len(named(ps, "surround")), 15)
        self.assertEqual(len([p for p in named(ps, "surround") if p["type"] == "prism"]), 12)
        self.assertEqual(len(named(ps, "keystone")), 1)
        cats = set(p["cat"] for p in ps)
        self.assertIn("windows/surrounds", cats)
        # surround proud of the wall face (world -y), never behind it
        for p in named(ps, "surround"):
            b = bbox(p)
            self.assertLess(b[1], 0)
            self.assertAlmostEqual(b[4], 0)

    def test_double_door_with_fanlight(self):
        ps = parts([{"k": "door", "box": [4, 0, 2.2, 3.6]}], style="plain")
        leaves = [p for p in ps if p.get("cat") == "doors/leaves"]
        self.assertEqual(len(leaves), 2 + 4)                 # two leaves, two panels each
        glass = [bbox(p) for p in ps if p.get("cat") == "doors/glass"]
        self.assertEqual(len(glass), 1)
        self.assertGreater(glass[0][2], 2.7)                # fanlight above the transom
        arched = parts([{"k": "door", "box": [4, 0, 2.2, 3.6], "shape": "arch"}], style="plain")
        fan = [p for p in arched if p.get("cat") == "doors/glass"]
        self.assertEqual(fan[0]["type"], "prism")           # the arch itself is glazed

    def test_pediment_tympanum_and_shutters_and_sign(self):
        ps = parts([{"k": "cornice", "box": [1, 9, 2, 0.6], "shape": "tri", "d": 0.3},
                    {"k": "blind", "box": [4, 5, 0.6, 2]},
                    {"k": "shop", "box": [6, 0, 5, 3.2]}])
        self.assertEqual(len(named(ps, "tympanum")), 1)
        tymp = bbox(named(ps, "tympanum")[0])
        self.assertAlmostEqual(tymp[1], -0.105)              # set back behind the raking cornices
        slats = named(ps, "slats")
        self.assertEqual(len(slats), 1)                      # all louvres in one profile
        self.assertEqual(slats[0]["type"], "prism")
        self.assertGreater(len(slats[0]["pts"]), 30)         # a tooth every 10 cm on 2 m
        sign = [p for p in ps if p.get("cat") == "shopfronts/signs"]
        self.assertEqual(len(sign), 1)
        self.assertAlmostEqual(bbox(sign[0])[5], 3.2)
        cut_top = max(bbox(c)[5] for c in ps[0]["cut"])     # shop on the ground line: cut, not hole
        self.assertLess(cut_top, 3.2 - 0.5)                  # the sign is wall, not opening

    def test_tall_sill_and_crown_split_into_parts(self):
        for style in ("plain", "classic"):
            ps = parts([{"k": "sill", "box": [1, 4, 1.6, 0.6]}, {"k": "cornice", "box": [1, 7.5, 1.8, 0.7]}], style=style)
            self.assertEqual(len(named(ps, "apron")), 1, style)
            self.assertEqual(len(named(ps, "frieze")), 1, style)
            slab_top = max(bbox(p)[5] for p in ps if p.get("cat") == "sills")
            self.assertAlmostEqual(slab_top, 4.6)
            apron = bbox(named(ps, "apron")[0])
            self.assertAlmostEqual(apron[2], 4.0)
            self.assertAlmostEqual(apron[5], 4.48)

    def test_door_surround_keeps_the_foot(self):
        ps = parts([{"k": "door", "box": [5, 0, 2, 3.4]}])
        self.assertEqual(len(named(ps, "surround")), 3)   # no bottom band
        self.assertAlmostEqual(min(bbox(p)[2] for p in named(ps, "leaf")), 0.06)   # frame on the ground line

    def test_plain_style_is_unchanged(self):
        ps = parts([{"k": "window", "box": [1, 5, 1.4, 2.6]}], style="plain")
        for got, want in zip(ps[0]["holes"][0][:4], [1.0, 5.0, 1.4, 2.6]):
            self.assertAlmostEqual(got, want)
        self.assertFalse(named(ps, "surround"))
        ps = parts([{"k": "window", "box": [1, 5, 1.4, 2.6], "sur": 0.1}], style="plain")
        self.assertEqual(len(named(ps, "surround")), 4)   # explicit surround still honoured

    def test_main_cornice_profile_and_dentils(self):
        ps = parts([{"k": "molding", "box": [0, 14, 12, 1], "d": 0.9}])
        prof = [p for p in ps if p["type"] == "prism"]
        self.assertEqual(len(prof), 1)
        b = bbox(prof[0])
        for got, want in zip(b, [0, -0.9, 14, 12, 0, 15]):
            self.assertAlmostEqual(got, want)
        dentils = named(ps, "dentil")
        self.assertGreater(len(dentils), 40)
        for d in dentils:
            db = bbox(d)
            self.assertTrue(0 <= db[0] and db[3] <= 12 + 1e-9)

    def test_balustrade_balcony(self):
        ps = parts([{"k": "balcony", "box": [2, 6, 3, 1.15], "d": 1.2}])
        self.assertGreaterEqual(len(named(ps, "console")), 3)
        balusters = named(ps, "baluster")
        self.assertGreater(len(balusters), 15)
        top = max(bbox(p)[5] for p in ps if "balcony" in p["name"])
        self.assertAlmostEqual(top, 7.15)
        self.assertEqual(set(p["cat"] for p in ps if "balcony" in p["name"]), {"balconies"})
        iron = parts([{"k": "balcony", "box": [2, 6, 3, 1.15], "rail": "iron"}])
        self.assertIn("balconies/railings", set(p["cat"] for p in iron))
        paths = set("::".join(layer_path("L", p, "it")) for p in iron)
        self.assertIn("L::F::Balconi::Ringhiere", paths)

    def test_pilaster_and_rustication(self):
        ps = parts([{"k": "pillar", "box": [0.2, 0, 0.6, 8]},
                    {"k": "door", "box": [5, 0, 2, 3.4]},
                    {"k": "rustic", "box": [0, 0, 12, 4.5]}])
        self.assertEqual(len(named(ps, "base")), 1)
        self.assertEqual(len(named(ps, "capital")), 1)
        courses = named(ps, "rustic")
        # 10 courses of 0.45 m; the 8 below the door head are split in two by it
        self.assertEqual(len(courses), 8 * 2 + 2)
        for c in courses:   # never across the door opening
            b = bbox(c)
            if b[2] < 3.4:
                self.assertTrue(b[3] <= 5 + 1e-9 or b[0] >= 7 - 1e-9, b)
        self.assertIn("rustication", set(p["cat"] for p in ps))

    def test_deco_shapes(self):
        ps = parts([{"k": "deco", "box": [1, 8, 0.3, 0.6], "shape": "console", "d": 0.4},
                    {"k": "deco", "box": [4, 8, 1.2, 0.8], "shape": "oval"},
                    {"k": "deco", "box": [7, 8, 1.5, 0.9], "shape": "panel", "d": 0.06}])
        deco = [p for p in ps if p.get("cat") == "ornaments"]
        self.assertEqual([p["type"] for p in deco], ["prism", "prism", "panel", "box"])
        console = bbox(deco[0])
        for got, want in zip(console, [1, -0.4, 8, 1.3, 0, 8.6]):
            self.assertAlmostEqual(got, want)
        oval = bbox(deco[1])
        self.assertAlmostEqual(oval[0], 4)
        self.assertAlmostEqual(oval[3], 5.2)
        with self.assertRaises(SpecError):
            parts([{"k": "deco", "box": [1, 1, 1, 1], "shape": "star"}])

    def test_quoins_alternate_on_the_corner_side(self):
        ps = parts([{"k": "quoin", "box": [0, 0, 0.8, 4.5]}, {"k": "quoin", "box": [11.2, 0, 0.8, 4.5]}])
        left = [bbox(p) for p in named(ps, "quoin") if bbox(p)[0] < 6]
        right = [bbox(p) for p in named(ps, "quoin") if bbox(p)[0] > 6]
        self.assertEqual(len(left), 10)
        self.assertTrue(all(abs(b[0]) < 1e-9 for b in left))           # flush with the left corner
        self.assertTrue(all(abs(b[3] - 12) < 1e-9 for b in right))     # flush with the right corner
        widths = [round(b[3] - b[0], 3) for b in left[:2]]
        self.assertEqual(widths, [0.8, 0.48])
        self.assertEqual(set(p["cat"] for p in named(ps, "quoin")), {"quoins"})

    def test_thin_rustication_never_inverts(self):
        for h in (0.01, 0.03, 0.05, 0.2):
            for c in named(parts([{"k": "rustic", "box": [0, 0, 3, h]}]), "rustic"):
                self.assertGreater(c["size"][2], 0, h)

    def test_whole_classic_facade_has_no_floating_parts(self):
        spec = {"units": "m", "parts": [{"type": "facade", "w": 12, "h": 15, "style": "classic", "els": [
            {"k": "rustic", "box": [0, 0, 12, 4]},
            {"k": "window", "box": [1, 5.5, 1.4, 2.6], "grid": [4, 2, 3, 4], "shape": "arch", "bars": [1, 1]},
            {"k": "cornice", "box": [0.8, 8.2, 1.8, 0.5], "grid": [4, 1, 3, 0], "shape": "tri"},
            {"k": "sill", "box": [0.9, 5.3, 1.6, 0.2], "grid": [4, 2, 3, 4]},
            {"k": "balcony", "box": [4, 5.3, 3.4, 1.15]},
            {"k": "molding", "box": [0, 14, 12, 1], "d": 0.9},
            {"k": "molding", "box": [0, 4.6, 12, 0.3], "d": 0.15},
            {"k": "door", "box": [5, 0, 2, 3.4], "shape": "arch"}]}]}
        out = check(spec)
        self.assertIn('"ok": true', out)
        self.assertNotIn("floating", out)

    def test_rejects(self):
        for el, where in (({"k": "sill", "box": [1, 1, 1, 0.1], "sur": 0.1}, ".sur"),
                          ({"k": "window", "box": [1, 1, 1, 1], "rail": "iron"}, ".rail"),
                          ({"k": "balcony", "box": [1, 1, 1, 1], "rail": "glass"}, ".rail")):
            with self.assertRaises(SpecError) as cm:
                parts([el])
            self.assertIn(where, str(cm.exception))
        with self.assertRaises(SpecError):
            parts([{"k": "window", "box": [1, 1, 1, 1]}], style="baroque")


if __name__ == "__main__":
    unittest.main()
