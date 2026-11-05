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
    def test_window_surround_goes_around_the_read_opening(self):
        ps = parts([{"k": "window", "box": [1, 5, 1.4, 2.6], "shape": "arch"}])
        wall = ps[0]
        self.assertEqual(len(wall["holes"]), 1)
        u, v, w, h = wall["holes"][0][:4]
        self.assertAlmostEqual(u, 1.0)       # the hole is the box read off the photo
        self.assertAlmostEqual(w, 1.4)
        self.assertAlmostEqual(h, 2.6)
        sb = [bbox(p) for p in named(ps, "surround")]
        self.assertAlmostEqual(min(b[0] for b in sb), 0.85)   # band outside the opening
        self.assertAlmostEqual(max(b[3] for b in sb), 2.55)
        # one band following the arch: the arched outline with the arched opening cut out
        band = named(ps, "surround")
        self.assertEqual(len(band), 1)
        self.assertEqual(band[0]["type"], "prism")
        self.assertGreater(len(band[0]["pts"]), 10)
        self.assertAlmostEqual(min(q[1] for q in band[0]["cut"][0]["pts"]), 5.0)   # sill band kept under it
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

    def test_surround_narrows_at_the_facade_edge(self):
        ps = parts([{"k": "window", "box": [0.05, 5, 1.2, 2.0]}])
        self.assertAlmostEqual(ps[0]["holes"][0][0], 0.05)
        self.assertGreaterEqual(min(bbox(p)[0] for p in named(ps, "surround")), -1e-9)

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
        band = named(ps, "surround")
        self.assertEqual(len(band), 1)
        self.assertLess(min(q[1] for q in band[0]["cut"][0]["pts"]), 0.0)   # no bottom band
        self.assertAlmostEqual(bbox(band[0])[2], 0.0)
        self.assertAlmostEqual(min(bbox(p)[2] for p in named(ps, "leaf")), 0.06)   # frame on the ground line

    def test_plain_style_is_unchanged(self):
        ps = parts([{"k": "window", "box": [1, 5, 1.4, 2.6]}], style="plain")
        for got, want in zip(ps[0]["holes"][0][:4], [1.0, 5.0, 1.4, 2.6]):
            self.assertAlmostEqual(got, want)
        self.assertFalse(named(ps, "surround"))
        ps = parts([{"k": "window", "box": [1, 5, 1.4, 2.6], "sur": 0.1}], style="plain")
        band = named(ps, "surround")                      # explicit surround still honoured
        self.assertEqual(len(band), 1)
        b = bbox(band[0])
        for got, want in zip([b[0], b[2], b[3], b[5]], [0.9, 4.9, 2.5, 7.7]):
            self.assertAlmostEqual(got, want)

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

    def test_surrounds_in_a_gable_and_down_to_the_foot(self):
        # A window in the gable (above the eaves at 15) and arched windows reaching the facade's
        # foot keep their surround: the gable one measured against the outline, the low ones open
        # at the foot like a door's.
        ps = parts([{"k": "window", "box": [5.5, 15.5, 1, 1.4]},
                    {"k": "window", "box": [1, 0, 1.4, 3], "shape": "arch", "sur": 0.3},
                    {"k": "window", "box": [9, 0.05, 1.4, 3], "shape": "arch", "sur": 0.3}], top=[[6, 19]])
        bands = dict((p["join"], p) for p in ps if p.get("cat") == "windows/surrounds" and "keystone" not in p["name"])
        self.assertEqual(sorted(bands), ["F window 0", "F window 1", "F window 2"])
        g = bbox(bands["F window 0"])
        self.assertAlmostEqual(g[0], 5.5 - 0.15)
        self.assertAlmostEqual(g[5], 16.9 + 0.15)
        for j in ("F window 1", "F window 2"):
            b = bands[j]
            self.assertAlmostEqual(bbox(b)[0], (1 if j.endswith("1") else 9) - 0.3)
            self.assertLess(min(q[1] for q in b["cut"][0]["pts"]), min(q[1] for q in b["pts"]))   # open foot
        hole = [h for h in ps[0]["holes"] + [c for c in ps[0].get("cut", [])] if isinstance(h, list)]
        self.assertTrue(any(abs(h[0] - 9) < 1e-9 and abs(h[2] - 1.4) < 1e-9 for h in hole))   # opening as read

    def test_bands_are_one_solid_each(self):
        # Surrounds, oculus rings and arched frames: one prism of the outer outline with the inner
        # outline cut out, never a ring of segments (their union is open and non-manifold in Rhino).
        els = [{"k": "window", "box": [1, 2, 1.2, 2.2], "shape": "arch"},
               {"k": "window", "box": [4, 2, 1.2, 2.2], "shape": "seg"},
               {"k": "window", "box": [7, 2, 1.0, 1.0], "shape": "round"},
               {"k": "window", "box": [9, 2, 1.0, 1.6]},
               {"k": "door", "box": [4, 6, 1.6, 2.8], "shape": "arch"}]
        ps = parts(els)
        for cat in ("windows/surrounds", "windows/frames", "doors/surrounds"):
            mine = [p for p in ps if p.get("cat") == cat and "keystone" not in p["name"]]
            per = {}
            for p in mine:
                per.setdefault(p["join"], []).append(p)
            for join, group in per.items():
                self.assertEqual(len(group), 1, (cat, join, [q["type"] for q in group]))
        arch_frames = [p for p in ps if p.get("cat") == "windows/frames" and p["join"] in ("F window 0", "F window 1")]
        self.assertEqual(len(arch_frames), 2)                          # arched windows get a frame too
        for p in ps:
            for c in p.get("cut", []):                                  # cutters pass right through
                if p["type"] == "prism" and c["type"] == "prism":
                    self.assertLess(c["at"][1], p["at"][1])
                    self.assertGreater(c["at"][1] + c["len"], p["at"][1] + p["len"])
        door = [p for p in ps if p.get("cat") == "doors/surrounds" and "keystone" not in p["name"]][0]
        self.assertLess(min(q[1] for q in door["cut"][0]["pts"]), 6.0)  # open at the foot: no band under a door

    def test_consoles_keep_clear_of_the_openings_below(self):
        # A balcony 30 cm over a window head (15 cm of it is the window's surround) and a French window
        # behind it: no console may hang over either opening or its surround; consoles beside the
        # window stay full length, and those over it keep only the free space or go.
        els = [{"k": "balcony", "box": [2, 6, 4, 1.1], "d": 1.0},
               {"k": "window", "box": [3.2, 3.9, 1.2, 1.8]},          # head at 5.7, surround to 5.85
               {"k": "window", "box": [3.2, 5.9, 1.2, 2.4]}]          # French window starting under the slab
        ps = parts(els)
        cons = [bbox(p) for p in named(ps, "console")]
        self.assertTrue(cons)
        ops = [bbox(p) for p in ps if p.get("cat", "").split("/")[0] == "windows"]
        for c in cons:
            for o in ops:
                clash = min(c[3], o[3]) - max(c[0], o[0]) > 1e-6 and min(c[5], o[5]) - max(c[2], o[2]) > 1e-6
                self.assertFalse(clash, (c, o))
        self.assertAlmostEqual(min(c[2] for c in cons), 6 - 0.6)       # clear of the window: full 60 cm
        # Nothing below: same consoles as before.
        alone = [bbox(p) for p in named(parts(els[:1]), "console")]
        self.assertEqual(len(alone), 5)
        self.assertLess(len(cons), 5)                                   # those over the window went
        self.assertTrue(all(abs(c[2] - 5.4) < 1e-9 for c in alone))

    def test_pilaster_and_rustication(self):
        ps = parts([{"k": "pillar", "box": [0.2, 0, 0.6, 8]},
                    {"k": "door", "box": [5, 0, 2, 3.4]},
                    {"k": "rustic", "box": [0, 0, 12, 4.5]}])
        self.assertEqual(len(named(ps, "base")), 1)
        self.assertEqual(len(named(ps, "capital")), 1)
        # The read box is the pilaster's widest outline (capital and base): nothing wider than it,
        # the shaft set in from it.
        pil = [bbox(p) for p in ps if p.get("cat") == "pillars"]
        self.assertAlmostEqual(min(b[0] for b in pil), 0.2)
        self.assertAlmostEqual(max(b[3] for b in pil), 0.8)
        shaft = bbox([p for p in ps if p.get("cat") == "pillars" and p["name"].split()[-1].isdigit()][0])
        self.assertGreater(shaft[0], 0.2 + 1e-3)
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
                          ({"k": "balcony", "box": [1, 1, 1, 1], "rail": "rope"}, ".rail")):
            with self.assertRaises(SpecError) as cm:
                parts([el])
            self.assertIn(where, str(cm.exception))
        with self.assertRaises(SpecError):
            parts([{"k": "window", "box": [1, 1, 1, 1]}], style="baroque")


if __name__ == "__main__":
    unittest.main()
