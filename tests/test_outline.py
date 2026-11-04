"""Second round of photo trials: the wall above the eaves (gables, stepped gables, raised parapets),
material zones, an element's own colour, door leaves, downpipes, and elements cut by the outline."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

from rhinospec import check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402
from rhinospec.naming import layer_path  # noqa: E402
from rhinospec.spec import SpecError  # noqa: E402

STEPS = [[2, 10], [2, 11], [4, 11], [4, 12], [6, 12], [6, 11], [8, 11], [8, 10]]


def facade(els, **kw):
    return dict({"type": "facade", "name": "F", "w": 10, "h": 10, "els": els}, **kw)


def parts(els, **kw):
    return validate({"units": "m", "parts": [facade(els, **kw)]})["parts"]


def of(ps, word):
    return [p for p in ps if word in p["name"].split()]


class Outline(unittest.TestCase):
    def test_stepped_gable_rises_with_its_coping(self):
        ps = parts([{"k": "window", "box": [1, 1, 1, 1]}], top=STEPS)
        top = [p for p in ps if p["name"] == "F wall top"]
        self.assertEqual(len(top), 1)
        self.assertAlmostEqual(max(q[1] for q in top[0]["pts"]), 12)
        self.assertEqual(top[0]["cat"], "walls")
        copings = of(ps, "coping")
        self.assertEqual(len(copings), 5)            # the five treads; risers have none
        self.assertTrue(all(p["cat"] == "cornices" for p in copings))
        self.assertAlmostEqual(max(bbox(p)[5] for p in copings), 12.08)

    def test_windows_in_the_gable_are_kept_and_cut_through_it(self):
        ps = parts([{"k": "window", "box": [4.5, 10.2, 1, 1.4], "shape": "arch"}], top=STEPS)
        self.assertTrue(of(ps, "glass"))
        top = [p for p in ps if p["name"] == "F wall top"][0]
        self.assertEqual(len(top["cut"]), 1)

    def test_window_across_a_step_is_cut_at_the_lower_tread(self):
        out = json.loads(check(json.dumps({"parts": [facade([{"k": "window", "box": [3, 10.2, 2, 1.5]}], top=STEPS)]})))
        self.assertIn("cut off", " ".join(out.get("notes", [])))

    def test_two_gables_with_a_valley_make_two_wall_pieces(self):
        ps = parts([{"k": "window", "box": [1, 1, 1, 1]}], top=[[2.5, 12], [5, 10], [7.5, 12]])
        self.assertEqual(len([p for p in ps if p["name"] == "F wall top"]), 2)

    def test_pixels_and_raised_parapet(self):
        ps = parts([{"k": "window", "box": [10, 50, 20, 80]}], px=[0, 20, 100, 120], top=[[40, 20], [40, 10], [60, 10], [60, 20]])
        top = [p for p in ps if p["name"] == "F wall top"][0]
        self.assertAlmostEqual(max(q[1] for q in top["pts"]), 11)

    def test_front_gable_roof_follows_the_outline_with_depth(self):
        ps = parts([{"k": "window", "box": [1, 1, 1, 1]}], top=[[5, 13]], depth=8, roof="gable")
        roof = [p for p in ps if p["name"] == "F roof"][0]
        self.assertAlmostEqual(max(q[1] for q in roof["pts"]), 13)
        self.assertAlmostEqual(roof["len"], 8 - 0.8)
        self.assertTrue([p for p in ps if p["name"] == "F back top"])

    def test_stepped_gable_roof_stays_under_the_steps(self):
        ps = parts([{"k": "window", "box": [1, 1, 1, 1]}], top=STEPS, depth=8, roof="gable")
        roof = [p for p in ps if p["name"] == "F roof"][0]
        (u0, _), (u1, _), (pu, pv) = roof["pts"]
        def roof_at(u):
            return 10 + (pv - 10) * (u - u0) / (pu - u0) if u <= pu else 10 + (pv - 10) * (u1 - u) / (u1 - pu)
        for u, v in STEPS:     # the inner step corners limit the pitch: the steps stand above the roof
            if v > 10:
                self.assertLessEqual(roof_at(u), v + 1e-9)
        self.assertGreater(pv, 11)

    def test_bad_outlines_are_rejected(self):
        for top, msg in (([[5, 9]], "at or above"), ([[6, 11], [4, 11]], "left to right"),
                         ([[5, 10]], "never rises"), ([[12, 11]], "outside")):
            with self.assertRaises(SpecError) as cm:
                parts([{"k": "window", "box": [1, 1, 1, 1]}], top=top)
            self.assertIn(msg, str(cm.exception))
        with self.assertRaises(SpecError):
            parts([{"k": "window", "box": [1, 1, 1, 1]}], top=[[5, 12]], depth=8, roof="hip")

    def test_block_faces_take_no_outline(self):
        with self.assertRaises(SpecError):
            validate({"parts": [{"type": "block", "w": 10, "d": 8, "h": 9,
                                 "faces": {"front": {"els": [{"k": "window", "box": [1, 1, 1, 1]}], "top": [[5, 12]]}}}]})

    def test_no_dormers_from_gable_windows(self):
        ps = parts([{"k": "window", "box": [4.5, 10.2, 1, 1]}], top=[[5, 13]], depth=8, roof="gable")
        self.assertFalse([p for p in ps if p.get("cat", "").startswith("roof/dormers")])


class Zones(unittest.TestCase):
    def test_cladding_zone_with_openings_cut_through(self):
        els = [{"k": "clad", "box": [0, 0, 10, 3]}, {"k": "window", "box": [1, 1, 1, 1]},
               {"k": "door", "box": [4, 0, 1, 2.2]}]
        ps = parts(els)
        clad = of(ps, "clad")[0]
        self.assertEqual(clad["cat"], "cladding")
        self.assertEqual(len(clad["holes"]), 1)      # the window inside the zone
        self.assertEqual(len(clad["cut"]), 1)        # the door on its edge
        self.assertEqual(layer_path("L", clad, "it")[-1], "Rivestimenti")

    def test_palette_clad_and_own_colour(self):
        els = [{"k": "clad", "box": [0, 0, 10, 3]}, {"k": "rustic", "box": [0, 3, 10, 1], "color": "#123456"},
               {"k": "window", "box": [1, 5, 1, 1], "color": "#222222"}]
        ps = parts(els, palette={"clad": "#8a857e", "trim": "#ffffff"})
        self.assertEqual(of(ps, "clad")[0]["color"], "#8a857e")
        self.assertTrue(all(p["color"] == "#123456" for p in of(ps, "rustic")))
        win = of(ps, "window")
        self.assertTrue(all(p["color"] == "#222222" for p in win if not p["cat"].endswith("/glass")))
        self.assertTrue(all(p.get("color") != "#222222" for p in win if p["cat"].endswith("/glass")))
        self.assertFalse([p for p in ps if "own_color" in p])

    def test_zone_inside_an_opening_is_not_built(self):
        ps = parts([{"k": "shop", "box": [1, 0, 4, 3]}, {"k": "clad", "box": [2, 0.5, 1, 1]}])
        self.assertFalse(of(ps, "clad"))

    def test_bad_colour_rejected(self):
        with self.assertRaises(SpecError):
            parts([{"k": "window", "box": [1, 1, 1, 1], "color": "red"}])


class Doors(unittest.TestCase):
    def test_glazed_door_has_glass_and_no_panels(self):
        ps = parts([{"k": "door", "box": [1, 0, 1.8, 2.2], "leaf": "glass", "bars": [1, 0]}])
        door = of(ps, "door")
        self.assertTrue([p for p in door if p["cat"] == "doors/glass"])
        self.assertFalse([p for p in door if p["cat"] == "doors/leaves"])

    def test_arched_glazed_door(self):
        ps = parts([{"k": "door", "box": [1, 0, 1.4, 2.8], "leaf": "glass", "shape": "arch"}])
        self.assertTrue([p for p in of(ps, "door") if p["cat"] == "doors/glass"])

    def test_garage_door_sections(self):
        ps = parts([{"k": "door", "box": [1, 0, 2.5, 2.1], "leaf": "garage"}])
        leaves = [p for p in of(ps, "door") if p["cat"] == "doors/leaves"]
        self.assertEqual(len(leaves), 4)             # one leaf and three grooves (four sections)

    def test_modern_panel_door_on_request(self):
        ps = parts([{"k": "door", "box": [1, 0, 1, 2.2], "leaf": "panel"}], style="modern")
        self.assertTrue([p for p in of(ps, "door") if p["cat"] == "doors/leaves"])

    def test_leaf_only_on_doors(self):
        with self.assertRaises(SpecError):
            parts([{"k": "window", "box": [1, 1, 1, 1], "leaf": "glass"}])
        with self.assertRaises(SpecError):
            parts([{"k": "door", "box": [1, 0, 1, 2], "leaf": "wood"}])


class Pipes(unittest.TestCase):
    def test_downpipe_is_tied_to_the_wall(self):
        out = json.loads(check(json.dumps({"parts": [facade([{"k": "pipe", "box": [5, 0, 0.12, 9]}])]})))
        self.assertTrue(out["ok"])
        self.assertNotIn("floating", out)
        ps = parts([{"k": "pipe", "box": [5, 0, 0.12, 9]}])
        self.assertEqual(len([p for p in of(ps, "pipe") if p["type"] == "cyl"]), 1)
        self.assertGreaterEqual(len(of(ps, "bracket")), 4)
        self.assertEqual(of(ps, "pipe")[0]["cat"], "downpipes")

    def test_gutter_runs_along(self):
        out = json.loads(check(json.dumps({"parts": [facade([{"k": "pipe", "box": [0, 9.8, 10, 0.15]}])]})))
        self.assertTrue(out["ok"])
        self.assertNotIn("floating", out)


if __name__ == "__main__":
    unittest.main()
