"""Pediments rise above the eaves; what sits in them is kept; nothing else vanishes silently."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402
from rhinospec.naming import layer_path  # noqa: E402


def facade(els, **kw):
    return dict({"type": "facade", "name": "F", "w": 20, "h": 12, "els": els}, **kw)


def parts(els, **kw):
    return validate({"units": "m", "parts": [facade(els, **kw)]})["parts"]


def of(ps, word):
    return [p for p in ps if word in p["name"].split()]


class Pediment(unittest.TestCase):
    def test_pediment_rises_above_the_eaves(self):
        ps = parts([{"k": "pediment", "box": [6, 11.5, 8, 3]}])
        ped = of(ps, "pediment")
        self.assertEqual(len(of(ped, "tympanum")), 1)
        self.assertAlmostEqual(max(bbox(p)[5] for p in ped), 14.5)   # 2.5 m above the 12 m eaves
        self.assertTrue(all(min(bbox(p)[1] for p in ped) < 0 for _ in ped))   # proud of the wall
        self.assertEqual(layer_path("L", ped[0], "it")[-1], "Timpani")

    def test_oculus_and_relief_in_the_tympanum_are_kept_in_front_of_it(self):
        els = [{"k": "pediment", "box": [6, 11.5, 8, 3]},
               {"k": "window", "box": [9.5, 12.2, 1, 1]},
               {"k": "deco", "box": [7.5, 12.0, 1.5, 0.8]}]
        ps = parts(els)
        tymp_front = min(bbox(p)[1] for p in of(ps, "tympanum"))
        for word in ("window", "deco"):
            mine = of(ps, word)
            self.assertTrue(mine, word)
            self.assertGreater(max(bbox(p)[5] for p in mine), 12.0, word)      # not clipped at the eaves
            self.assertLess(min(bbox(p)[1] for p in mine), tymp_front + 1e-6, word)   # on the tympanum, not hidden in it
        self.assertNotIn("notes", validate({"units": "m", "parts": [facade(els)]}))

    def test_elements_lost_outside_the_facade_are_reported(self):
        spec = {"units": "m", "parts": [facade([{"k": "window", "box": [2, 2, 1, 1.5]},
                                               {"k": "window", "box": [2, 13, 1, 1]}])]}
        out = json.loads(check(spec))
        self.assertTrue(out["ok"])
        self.assertIn("1 element(s) outside", out["notes"][0])

    def test_deep_oculus_still_sits_on_the_tympanum(self):
        # A window's d is its recess, capped by the wall: lifting it onto the tympanum must use the
        # same cap, or a deep one floats in front of the pediment.
        for d in (0.12, 0.3, 1.0):
            ps = parts([{"k": "pediment", "box": [6, 11.5, 8, 3]}, {"k": "window", "box": [9.5, 12.2, 1, 1], "d": d}])
            tymp = min(bbox(p)[1] for p in of(ps, "tympanum"))
            win = [bbox(p) for p in of(ps, "window")]
            self.assertGreaterEqual(max(b[4] for b in win), tymp - 1e-6, d)    # touching or set in it
            self.assertLess(min(b[1] for b in win), tymp, d)                   # showing in front

    def test_only_oculi_reliefs_and_mouldings_live_in_a_pediment(self):
        # An arcade, a door or a balcony read inside a pediment's box above the eaves would hang in
        # the air (a portico recess behind a tympanum): dropped and noted like anything above the eaves.
        els = [{"k": "pediment", "box": [6, 11.5, 8, 3]},
               {"k": "window", "box": [9.5, 12.2, 1, 1]},
               {"k": "arcade", "box": [7, 12.1, 1, 0.8], "d": 1.5},
               {"k": "door", "box": [11.5, 12.1, 0.8, 1.0]},
               {"k": "balcony", "box": [12.5, 12.1, 1, 0.5]}]
        ps = parts(els)
        self.assertTrue(of(ps, "window"))
        for word in ("arcade", "door", "balcony"):
            self.assertFalse(of(ps, word), word)
        out = json.loads(check({"units": "m", "parts": [facade(els)]}))
        self.assertIn("3 element(s) outside", out["notes"][0])

    def test_pediment_must_rest_on_the_wall(self):
        # A grid of pediments read by mistake: the upper rows would float above the eaves.
        els = [{"k": "pediment", "box": [2, 11.5, 4, 2], "grid": [2, 3, 8, 3]},
               {"k": "window", "box": [3.5, 17.8, 1, 1]}]          # an oculus inside a floating one
        ps = parts(els)
        self.assertEqual(len(of(ps, "tympanum")), 2)                # only the bottom row is built
        self.assertTrue(all(bbox(p)[2] < 12 for p in of(ps, "pediment")))
        self.assertFalse(of(ps, "window"))                           # nothing kept up in the air
        out = json.loads(check({"units": "m", "parts": [facade(els)]}))
        self.assertIn("5 element(s) outside", out["notes"][0])
        # On a gable the wall top is higher: a pediment sitting on the gable's slope still counts.
        on_gable = parts([{"k": "pediment", "box": [8, 14, 4, 2]}], top=[[10, 16]])
        self.assertEqual(len(of(on_gable, "tympanum")), 1)

    def test_pavilion_pediment_and_its_cornice(self):
        # A pavilion rising above a low parapet (risers at u = 4 and u = 10): the pediment sits on
        # its top, and the cornice crowning it overhangs its sides a little, as built.
        top = [[0, 13], [4, 13], [4, 15], [10, 15], [10, 13], [20, 13]]
        els = [{"k": "pediment", "box": [4, 15, 6, 2]},
               {"k": "molding", "box": [3.85, 14.8, 6.3, 0.25]},
               {"k": "window", "box": [4.5, 13.5, 1, 1]}]                 # a window in the pavilion
        ps = parts(els, top=top)
        self.assertEqual(len(of(ps, "tympanum")), 1)
        self.assertTrue(of(ps, "window"))
        # an opening straddling the riser is still cut at the lower wall, not let out
        cut = parts([{"k": "window", "box": [3.8, 13.5, 1, 1]}], top=top)
        self.assertFalse(of(cut, "window"))
        mould = [bbox(p) for p in of(ps, "molding")]
        self.assertTrue(mould)
        self.assertAlmostEqual(min(b[0] for b in mould), 3.85)
        self.assertAlmostEqual(max(b[3] for b in mould), 10.15)
        out = json.loads(check({"units": "m", "parts": [facade(els, top=top)]}))
        self.assertNotIn("outside", " ".join(out.get("notes", [])))

    def test_pediment_on_a_deep_facade_with_a_hip_roof(self):
        ps = parts([{"k": "pediment", "box": [6, 11.5, 8, 3]}], depth=12, roof="hip", roof_h=4, dormers=3)
        self.assertTrue(of(ps, "tympanum"))
        self.assertTrue([p for p in ps if p.get("cat") == "roof/dormers"])


class Joined(unittest.TestCase):
    def test_every_element_is_one_join_group(self):
        ps = parts([{"k": "blind", "box": [2, 2, 0.6, 1.6]}, {"k": "blind", "box": [4, 2, 0.6, 1.6]}], style="classic")
        groups = set(p["join"] for p in ps if p.get("cat") == "shutters")
        self.assertEqual(len(groups), 2)                      # one solid per shutter
        self.assertGreater(len([p for p in ps if p.get("cat") == "shutters"]), 2)


class Surround(unittest.TestCase):
    def test_classic_hole_matches_the_read_box(self):
        ps = parts([{"k": "window", "box": [3, 4, 1.2, 2.2]}], style="classic")
        self.assertEqual([round(x, 6) for x in ps[0]["holes"][0][:4]], [3, 4, 1.2, 2.2])


class Oculus(unittest.TestCase):
    def test_round_window_is_a_ring_and_round_glass(self):
        from rhinospec.plan import opening_outline
        ps = parts([{"k": "window", "box": [9, 6, 1.2, 1.2], "shape": "round"}], style="classic")
        self.assertEqual(ps[0]["holes"][0][4], 3)                         # round hole in the wall
        glass = [p for p in ps if p.get("cat") == "windows/glass"]
        self.assertEqual(len(glass), 1)
        self.assertEqual(len(glass[0]["pts"]), 24)
        b = bbox(glass[0])
        self.assertAlmostEqual(b[3] - b[0], b[5] - b[2], places=6)        # a circle in a square box
        self.assertTrue(of(ps, "keystone"))
        pts = opening_outline(0, 0, 2, 1, "round")
        self.assertAlmostEqual(max(p[0] for p in pts) - min(p[0] for p in pts), 2.0, places=6)

    def test_round_is_for_windows_only(self):
        from rhinospec import SpecError
        with self.assertRaises(SpecError):
            parts([{"k": "door", "box": [9, 0, 1.2, 1.2], "shape": "round"}])


class Railings(unittest.TestCase):
    def test_glass_parapet_has_panes_posts_and_a_handrail(self):
        ps = parts([{"k": "balcony", "box": [2, 3, 6, 1.1], "d": 1.2, "rail": "glass"}])
        panes = [p for p in ps if p.get("cat") == "balconies/glass"]
        metal = [p for p in ps if p.get("cat") == "balconies/railings"]
        self.assertEqual(len(panes), 3)                                    # front and two sides
        self.assertTrue(of(metal, "handrail") and of(metal, "post"))
        top = max(bbox(p)[5] for p in metal)
        self.assertAlmostEqual(top, 4.1)                                   # the rail height read off the photo
        self.assertTrue(all(bbox(p)[5] <= top + 1e-9 for p in panes))

    def test_iron_bars_are_slim(self):
        ps = parts([{"k": "balcony", "box": [2, 3, 6, 1.1], "rail": "iron"}])
        bar = of(ps, "bar")[0]
        self.assertLessEqual(bar["size"][0], 0.016 + 1e-9)


class RoundPillar(unittest.TestCase):
    def test_round_pier_is_a_cylinder_in_front_of_the_wall(self):
        ps = parts([{"k": "pillar", "box": [4, 0, 0.6, 6], "shape": "round"}])
        shaft = [p for p in ps if p.get("cat") == "pillars"]
        self.assertEqual([p["type"] for p in shaft], ["cyl"])
        b = bbox(shaft[0])
        self.assertAlmostEqual(b[3] - b[0], 0.6)
        self.assertAlmostEqual(b[4], 0.0)          # touches the wall face, stands in front of it

    def test_engaged_column_with_base_and_capital(self):
        ps = parts([{"k": "pillar", "box": [4, 3, 0.8, 6], "shape": "round", "d": 0.5}], style="classic")
        cols = [p for p in ps if p.get("cat") == "pillars"]
        self.assertEqual(len(cols), 3)
        # The read box is the widest outline (the capital): it stands out by d and spans the box;
        # the shaft is thinner, on the same axis.
        self.assertAlmostEqual(min(bbox(p)[1] for p in cols), -0.5)
        self.assertAlmostEqual(min(bbox(p)[0] for p in cols), 4.0)
        self.assertAlmostEqual(max(bbox(p)[3] for p in cols), 4.8)
        shaft = bbox([p for p in cols if p["name"].split()[-1].isdigit()][0])
        self.assertLess(shaft[3] - shaft[0], 0.8 - 1e-3)
        self.assertAlmostEqual((shaft[0] + shaft[3]) / 2, 4.4)


class Arcade(unittest.TestCase):
    def test_portico_is_open_with_a_recessed_back_wall(self):
        els = [{"k": "arcade", "box": [1 + 3.5 * i, 0, 2.6, 4.5], "shape": "arch", "d": 3.0} for i in range(5)]
        els.append({"k": "door", "box": [8.6, 0, 1.4, 2.6]})            # read inside the third arch
        ps = parts(els)
        arc = [p for p in ps if p.get("cat") == "arcades"]
        back = of(arc, "back")
        self.assertEqual(len(back), 1)                                     # one back wall for the row
        self.assertEqual(len(back[0]["holes"]), 1)                         # with a hole for the door
        self.assertAlmostEqual(bbox(back[0])[1], 3.0)
        self.assertEqual(len(of(arc, "ceiling")), 1)
        self.assertEqual(len(of(arc, "side")), 2)
        self.assertFalse([p for p in ps if p["name"].startswith("F arcade") and p.get("cat", "").endswith("glass")])
        door = [p for p in ps if p.get("cat", "").startswith("doors")]
        self.assertTrue(door and min(bbox(p)[1] for p in door) >= 3.0 - 1e-6)   # on the back wall, not in the arch

    def test_overlapping_doors_in_an_arcade_merge_into_one_hole(self):
        els = [{"k": "arcade", "box": [1, 0, 6, 4], "d": 3},
               {"k": "door", "box": [2, 0, 2, 2.5]}, {"k": "window", "box": [3, 1, 2, 1.5]}]
        back = of(parts(els), "back")[0]
        self.assertEqual(len(back["holes"]), 1)

    def test_arcade_shapes(self):
        from rhinospec import SpecError
        with self.assertRaises(SpecError):
            parts([{"k": "arcade", "box": [1, 0, 2, 3], "shape": "round"}])


class Modern(unittest.TestCase):
    def test_modern_doors_are_glass_and_profiles_dark_and_slim(self):
        ps = parts([{"k": "door", "box": [4, 0, 1.2, 2.4]}, {"k": "window", "box": [8, 3, 1.4, 1.4]},
                    {"k": "spandrel", "box": [7, 2.2, 3, 0.7]}], style="modern")
        self.assertTrue([p for p in ps if p.get("cat") == "doors/glass"])
        self.assertFalse([p for p in ps if p.get("cat") == "doors/leaves"])
        frame = [p for p in ps if p.get("cat") == "windows/frames"][0]
        self.assertAlmostEqual(frame["holes"][0][0], 0.04)
        self.assertEqual(frame["color"], "#3a3d42")
        self.assertTrue([p for p in ps if p.get("cat") == "spandrels"])


class RoofFromPhoto(unittest.TestCase):
    def test_windows_above_the_eaves_become_dormers_where_they_are(self):
        # px facade 1000 x 500 px for 20 x 10 m (50 px per m), eaves at the top of px
        f = {"type": "facade", "name": "F", "h": 10, "px": [0, 100, 1000, 600], "depth": 12, "roof": "hip",
             "roof_h": 4, "chimneys": [250, 750],
             "els": [{"k": "window", "box": [100, 300, 160, 400]},
                     {"k": "window", "box": [300, 40, 340, 90]}, {"k": "window", "box": [700, 40, 740, 90]},
                     {"k": "blind", "box": [285, 40, 298, 90]}]}
        out = validate({"units": "m", "parts": [f]})
        self.assertNotIn("notes", out)                                     # dormer windows are not "lost"
        ps = out["parts"]
        dorm = [p for p in ps if p.get("cat") == "roof/dormers" and p["type"] == "box"]
        self.assertEqual(len(dorm), 2)                                     # two, on the front slope only
        mids = sorted((bbox(p)[0] + bbox(p)[3]) / 2.0 for p in dorm)
        self.assertAlmostEqual(mids[0], 6.4, places=1)                     # under the windows at x 320 and 720 px
        self.assertAlmostEqual(mids[1], 14.4, places=1)
        chim = [p for p in ps if p.get("cat") == "roof/chimneys" and "cap" not in p["name"]]
        self.assertEqual(sorted(round((bbox(p)[0] + bbox(p)[3]) / 2.0, 3) for p in chim), [5.0, 15.0])
        self.assertFalse([p for p in ps if p.get("cat") == "shutters" and bbox(p)[5] > 10.0])

    def test_dormer_windows_without_a_roof_are_still_reported(self):
        f = {"type": "facade", "name": "F", "h": 10, "px": [0, 100, 1000, 600],
             "els": [{"k": "window", "box": [300, 40, 340, 90]}]}
        self.assertIn("notes", validate({"units": "m", "parts": [f]}))


class SmallArches(unittest.TestCase):
    def test_tiny_arched_door_with_a_wide_surround_does_not_crash(self):
        # found by tools/fuzz_specs.py: the archivolt's inner outline degenerated to a rectangle
        for k in ("door", "window"):
            ps = parts([{"k": k, "box": [3, 0 if k == "door" else 3, 0.5, 0.2], "shape": "arch", "sur": 0.35}],
                       style="classic")
            self.assertTrue(of(ps, "surround"))


class BlockParity(unittest.TestCase):
    """A block does what a facade does: dormers from the photo, chimney positions, notes."""

    def block(self, **kw):
        b = dict({"type": "block", "name": "B", "w": 20, "d": 12, "h": 10, "roof": "hip", "roof_h": 4,
                  "faces": {"front": {"px": [0, 100, 1000, 600],
                                      "els": [{"k": "window", "box": [100, 300, 160, 400]},
                                              {"k": "window", "box": [300, 40, 340, 90]}]},
                            "right": {"px": [0, 100, 600, 600],
                                      "els": [{"k": "window", "box": [100, 40, 160, 90]}]}}}, **kw)
        return validate({"units": "m", "parts": [b]})

    def test_block_front_dormers_chimneys_and_notes(self):
        out = self.block(chimneys=[4, 16])
        dorm = [p for p in out["parts"] if p.get("cat") == "roof/dormers" and p["type"] == "box"]
        self.assertEqual(len(dorm), 1)
        self.assertAlmostEqual((bbox(dorm[0])[0] + bbox(dorm[0])[3]) / 2.0, 6.4, places=1)
        chim = [p for p in out["parts"] if p.get("cat") == "roof/chimneys" and "cap" not in p["name"]]
        self.assertEqual(sorted(round((bbox(p)[0] + bbox(p)[3]) / 2.0, 3) for p in chim), [4.0, 16.0])
        self.assertEqual(len(out["notes"]), 1)               # the right face's window above its eaves
        self.assertIn("faces.right", out["notes"][0])

    def test_block_chimney_positions_are_checked(self):
        from rhinospec import SpecError
        with self.assertRaises(SpecError):
            self.block(chimneys=[30])


class Palette(unittest.TestCase):
    def test_photo_colours_reach_each_family(self):
        pal = {"wall": "#8a8f94", "shutters": "#6f8fa6", "glass": "#2f3b46", "frames": "#ffffff", "trim": "#c9c2b5",
               "roof": "#9c4a32", "doors": "#5a3b25"}
        ps = parts([{"k": "window", "box": [2, 3, 1.2, 2]}, {"k": "blind", "box": [3.3, 3, 0.6, 2]},
                    {"k": "door", "box": [8, 0, 1.2, 2.4]}, {"k": "molding", "box": [0, 6, 20, 0.4]}],
                   style="classic", palette=pal, depth=10, roof="hip")
        col = lambda cat: set(p.get("color") for p in ps if p.get("cat") == cat)
        self.assertEqual(col("walls"), {"#8a8f94"})
        self.assertEqual(col("shutters"), {"#6f8fa6"})
        self.assertEqual(col("windows/glass"), {"#2f3b46"})
        self.assertEqual(col("windows/frames"), {"#ffffff"})
        self.assertEqual(col("mouldings"), {"#c9c2b5"})
        self.assertEqual(col("doors/leaves"), {"#5a3b25"})
        self.assertEqual(col("roof"), {"#9c4a32"})

    def test_bad_palette_is_refused(self):
        from rhinospec import SpecError
        for pal in ({"walls": "#ffffff"}, {"wall": "white"}, ["#ffffff"]):
            with self.assertRaises(SpecError):
                parts([{"k": "window", "box": [2, 3, 1, 1]}], palette=pal)


if __name__ == "__main__":
    unittest.main()
