"""Tests for the pure-Python part of rhinospec (validation and building planning).

Run: python -m unittest discover -s tests -p "test_*.py"
"""
import json
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))

import rhinospec  # noqa: E402
from rhinospec import SpecError, validate  # noqa: E402


def spec(*parts, **kw):
    s = {"units": "m", "parts": list(parts)}
    s.update(kw)
    return s


class Primitives(unittest.TestCase):
    def test_defaults(self):
        out = validate(spec({"type": "box", "size": [1, 2, 3]}))
        self.assertEqual(out["units"], "m")
        self.assertEqual(out["layer"], "Model")
        self.assertFalse(out["clear"])
        p = out["parts"][0]
        self.assertEqual(p["at"], [0.0, 0.0, 0.0])
        self.assertEqual(p["rot"], 0.0)

    def test_every_primitive(self):
        sq = [[0, 0], [1, 0], [1, 1], [0, 1]]
        parts = [
            {"type": "box", "size": [1, 1, 1]},
            {"type": "cyl", "r": 1, "h": 2},
            {"type": "cone", "r": 1, "h": 2, "r2": 0.5},
            {"type": "sphere", "r": 1},
            {"type": "torus", "R": 2, "r": 0.5},
            {"type": "extrude", "pts": sq, "h": 1},
            {"type": "prism", "pts": [[0, 0], [2, 0], [1, 1]], "len": 3},
            {"type": "revolve", "profile": [[0, 0], [1, 0], [1, 2], [0, 2]]},
            {"type": "loft", "sections": [{"pts": sq, "z": 0}, {"pts": sq, "z": 1}]},
            {"type": "pipe", "path": [[0, 0, 0], [1, 1, 1]], "r": 0.1},
        ]
        self.assertEqual(len(validate(spec(*parts))["parts"]), 10)

    def test_closed_polygon_is_tolerated(self):
        p = validate(spec({"type": "extrude", "pts": [[0, 0], [1, 0], [1, 1], [0, 0]], "h": 1}))["parts"][0]
        self.assertEqual(len(p["pts"]), 3)

    def test_cut_and_color(self):
        p = validate(spec({"type": "box", "size": [2, 2, 2], "color": "#FF0000",
                           "cut": [{"type": "cyl", "r": 0.5, "h": 3}]}))["parts"][0]
        self.assertEqual(p["color"], "#ff0000")
        self.assertEqual(p["cut"][0]["type"], "cyl")

    def test_keep_intersects_views(self):
        # a front elevation extruded through the depth, kept inside the side profile
        front = {"type": "prism", "pts": [[0, 0], [10, 0], [10, 30], [0, 12]], "len": 8,
                 "keep": [{"type": "prism", "rot": 90, "at": [11, 0, 0], "len": 12,
                           "pts": [[0, 0], [8, 0], [8, 20], [0, 30]]}]}
        p = validate(spec(front))["parts"][0]
        self.assertEqual(p["keep"][0]["type"], "prism")
        self.assertEqual(p["keep"][0]["at"], [11, 0, 0])
        inner = {"type": "box", "size": [1, 1, 1], "keep": [{"type": "sphere", "r": 1}]}
        with self.assertRaisesRegex(SpecError, "own keep parts"):
            validate(spec({"type": "box", "size": [2, 2, 2], "cut": [inner]}))
        with self.assertRaisesRegex(SpecError, "expected 1.."):
            validate(spec({"type": "box", "size": [2, 2, 2], "keep": []}))
        with self.assertRaisesRegex(SpecError, "expected 1.."):
            validate(spec({"type": "box", "size": [2, 2, 2], "keep": {"type": "sphere", "r": 1}}))


class Rejections(unittest.TestCase):
    def bad(self, s, fragment):
        with self.assertRaises(SpecError) as cm:
            validate(s)
        self.assertIn(fragment, str(cm.exception))

    def test_unknown_type(self):
        self.bad(spec({"type": "python", "code": "x"}), "parts[0].type")

    def test_unknown_key(self):
        self.bad(spec({"type": "box", "size": [1, 1, 1], "exec": "x"}), "unknown key")

    def test_unknown_top_key(self):
        self.bad({"parts": [{"type": "sphere", "r": 1}], "script": "x"}, "unknown key")

    def test_numbers(self):
        self.bad(spec({"type": "box", "size": [1, 1, 0]}), "> 0")
        self.bad(spec({"type": "box", "size": [1, 1, float("nan")]}), "finite")
        self.bad(spec({"type": "box", "size": [1, 1, 1e9]}), "out of range")
        self.bad(spec({"type": "box", "size": [1, 1, True]}), "number")
        self.bad(spec({"type": "box", "size": [1, 1, "2"]}), "number")

    def test_names_and_layers(self):
        self.bad(spec({"type": "sphere", "r": 1, "name": "a::b"}), ".name")
        self.bad(spec({"type": "sphere", "r": 1}, layer="Default::x"), "spec.layer")
        self.bad(spec({"type": "sphere", "r": 1}, layer="x" * 65), "spec.layer")
        self.bad(spec({"type": "sphere", "r": 1}, units="inch"), "spec.units")

    def test_geometry_rules(self):
        self.bad(spec({"type": "torus", "R": 1, "r": 1}), "smaller than R")
        self.bad(spec({"type": "extrude", "pts": [[0, 0], [1, 1], [2, 2]], "h": 1}), "zero area")
        self.bad(spec({"type": "revolve", "profile": [[-1, 0], [1, 1]]}), "radius")
        sq = [[0, 0], [1, 0], [1, 1]]
        self.bad(spec({"type": "loft", "sections": [{"pts": sq, "z": 1}, {"pts": sq, "z": 1}]}), "rise")

    def test_loft_point_count(self):
        tri, sq = [[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 0], [1, 1], [0, 1]]
        self.bad(spec({"type": "loft", "sections": [{"pts": tri, "z": 0}, {"pts": sq, "z": 1}]}), "same number")

    def test_quotes_cannot_reach_the_python_literal(self):
        # The skill embeds the spec in r'''...'''. Every free-text field is regex-limited,
        # so a spec that validates can never carry a quote or backslash.
        for field in ("a'b", 'a"b', "a\\b", "a\nb", "ab\n", "x'''"):
            self.bad(spec({"type": "sphere", "r": 1, "name": field}), ".name")
            self.bad(spec({"type": "sphere", "r": 1}, layer=field), "spec.layer")

    def test_nested_cuts_rejected(self):
        inner = {"type": "box", "size": [1, 1, 1], "cut": [{"type": "sphere", "r": 1}]}
        self.bad(spec({"type": "box", "size": [2, 2, 2], "cut": [inner]}), "cannot have their own cuts")

    def test_part_limit(self):
        many = {"type": "array", "of": {"type": "sphere", "r": 1}, "n": [50, 50, 1], "step": [3, 3, 0]}
        self.bad(spec(many), "part limit")
        self.bad(spec(*([{"type": "sphere", "r": 1}] * 2001)), "part limit")

    def test_point_limit(self):
        pts = [[math.cos(i), math.sin(i)] for i in range(501)]
        self.bad(spec({"type": "extrude", "pts": pts, "h": 1}), "points")

    def test_empty_and_non_object(self):
        self.bad(spec(), "non-empty")
        self.bad(spec("box"), "expected an object")


class Arrays(unittest.TestCase):
    def test_grid(self):
        parts = validate(spec({"type": "array", "of": {"type": "cyl", "r": 0.2, "h": 3, "at": [1, 1, 0]},
                               "n": [3, 2, 1], "step": [5, 4, 0]}))["parts"]
        self.assertEqual(len(parts), 6)
        self.assertEqual(parts[-1]["at"], [11.0, 5.0, 0.0])
        # copies must not share the "at" list
        parts[0]["at"][0] = 99
        self.assertEqual(parts[1]["at"][0], 6.0)


class Buildings(unittest.TestCase):
    rect = [[0, 0], [10, 0], [10, 6], [0, 6]]

    def build(self, **kw):
        b = {"type": "building", "footprint": self.rect, "floors": 2, "floor_h": 3, "wall_t": 0.3,
             "slab_t": 0.2, "name": "casa"}
        b.update(kw)
        return validate(spec(b))["parts"]

    def test_opening_errors_name_the_part(self):
        too_many = [{"wall": 0, "offset": 1, "width": 2, "height": 1, "sill": 1, "count": 5, "gap": 1}]
        with self.assertRaisesRegex(SpecError, r"^parts\[0\]\.openings\[0\]: copy 3 ends at"):
            self.build(openings=too_many)
        too_tall = [{"wall": 0, "offset": 1, "width": 1, "height": 3, "sill": 1}]
        with self.assertRaisesRegex(SpecError, r"^parts\[0\]\.openings\[0\]: sill \+ height"):
            self.build(openings=too_tall)

    def test_counts(self):
        parts = self.build()
        # per floor: 1 slab + 4 walls, then roof slab
        self.assertEqual(len(parts), 2 * 5 + 1)
        self.assertEqual(parts[-1]["name"], "casa roof slab")
        self.assertEqual(parts[-1]["at"][2], 6.0)

    def test_walls_follow_edges(self):
        walls = [p for p in self.build(floors=1) if "wall" in p.get("name", "")]
        self.assertEqual([round(w["size"][0], 6) for w in walls], [10, 6, 10, 6])
        self.assertEqual([round(w["rot"]) for w in walls], [0, 90, 180, -90])
        self.assertAlmostEqual(walls[0]["size"][2], 2.8)

    def test_clockwise_footprint_is_normalised(self):
        cw = list(reversed(self.rect))
        walls = [p for p in self.build(floors=1, footprint=cw) if "wall" in p.get("name", "")]
        self.assertEqual([round(w["rot"]) for w in walls], [0, 90, 180, -90])

    def test_openings(self):
        parts = self.build(floors=1, openings=[{"wall": 0, "offset": 1, "width": 1, "height": 1.2,
                                                "sill": 0.9, "count": 3, "gap": 2}])
        wall = parts[1]
        self.assertEqual(len(wall["cut"]), 3)
        first = wall["cut"][0]
        self.assertAlmostEqual(first["at"][0], 1.0)
        self.assertAlmostEqual(first["at"][1], -0.15)   # starts outside the wall
        self.assertAlmostEqual(first["at"][2], 0.2 + 0.9)
        self.assertEqual(first["size"], [1.0, 0.6, 1.2])
        self.assertNotIn("cut", parts[2])

    def test_opening_on_one_floor(self):
        parts = self.build(openings=[{"wall": 1, "floor": 1}])
        cut_walls = [p["name"] for p in parts if "cut" in p]
        self.assertEqual(cut_walls, ["casa wall 1.1"])

    def test_opening_errors(self):
        with self.assertRaises(SpecError):
            self.build(openings=[{"wall": 0, "offset": 9.5, "width": 1}])
        with self.assertRaises(SpecError):
            self.build(openings=[{"wall": 0, "sill": 2, "height": 1}])
        with self.assertRaises(SpecError):
            self.build(openings=[{"wall": 4}])
        with self.assertRaises(SpecError):
            self.build(openings=[{"wall": 0, "floor": 2}])

    def test_gable(self):
        roof = self.build(roof="gable", roof_h=2)[-1]
        self.assertEqual(roof["type"], "prism")
        self.assertEqual(roof["rot"], -90.0)      # ridge along the 10 m side
        self.assertEqual(roof["len"], 10)
        self.assertEqual(roof["pts"][2], [3.0, 2])
        validate(spec(roof))  # the planned part is itself a valid primitive

    def test_planned_parts_revalidate(self):
        parts = self.build(roof="gable", openings=[{"wall": 2, "count": 2}])
        validate(spec(*parts))

    def test_slab_thicker_than_floor(self):
        with self.assertRaises(SpecError):
            self.build(slab_t=3)


class Entry(unittest.TestCase):
    def test_check_ok(self):
        out = json.loads(rhinospec.check('{"parts":[{"type":"sphere","r":1}]}'))
        self.assertEqual(out, {"ok": True, "parts": 1})

    def test_check_reports_errors_as_json(self):
        self.assertFalse(json.loads(rhinospec.check("{not json"))["ok"])
        self.assertIn("spec.v", json.loads(rhinospec.check('{"v":2,"parts":[]}'))["error"])

    def test_run_rejects_before_touching_rhino(self):
        # Invalid specs must fail in validation, without importing RhinoCommon.
        out = json.loads(rhinospec.run('{"parts":[{"type":"box","size":[0,1,1]}]}'))
        self.assertFalse(out["ok"])
        self.assertNotIn("rhinospec.build", sys.modules)


if __name__ == "__main__":
    unittest.main()
