"""Tests for facades, panels and the CMP benchmark helpers (pure Python, no Rhino, no dataset)."""
import os
import sys
import time
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "rhino"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "dev"))

from rhinospec import SpecError, validate  # noqa: E402
from rhinospec.plan import _merge_rects, facade_elements  # noqa: E402
from rhinospec.spec import _facade  # noqa: E402
import facade_bench as fb  # noqa: E402


def facade(**kw):
    f = {"type": "facade", "w": 10, "h": 9, "els": [{"k": "window", "box": [1, 1, 1, 1.5]}]}
    f.update(kw)
    return dict((k, v) for k, v in f.items() if v is not None)


def parts(*ps):
    return validate({"units": "m", "parts": list(ps)})["parts"]


class Panels(unittest.TestCase):
    def test_valid(self):
        p = parts({"type": "panel", "size": [4, 3], "t": 0.3, "holes": [[1, 1, 1, 1], [2.5, 1, 1, 1]]})[0]
        self.assertEqual(len(p["holes"]), 2)

    def test_hole_rules(self):
        for holes, msg in (([[0, 1, 1, 1]], "strictly inside"), ([[3.5, 1, 1, 1]], "strictly inside"),
                           ([[1, 1, 1, 1], [1.5, 1.5, 1, 1]], "overlaps"), ([[1, 1, 1, 1], [2, 1, 1, 1]], "touches"), ([[1, 1, 0, 1]], "> 0")):
            with self.assertRaises(SpecError) as cm:
                parts({"type": "panel", "size": [4, 3], "t": 0.3, "holes": holes})
            self.assertIn(msg, str(cm.exception))


class Facades(unittest.TestCase):
    def test_window_details(self):
        ps = parts(facade(els=[{"k": "window", "box": [1, 1, 1, 1.5], "bars": [1, 2]}]))
        names = [p["name"] for p in ps]
        self.assertEqual(names[0], "facade wall")
        self.assertEqual(ps[0]["holes"], [[1.0, 1.0, 1.0, 1.5]])
        self.assertEqual(sum("frame" in n for n in names), 1)
        self.assertEqual(sum("glass" in n for n in names), 1)
        self.assertEqual(sum("bar" in n for n in names), 3)

    def test_grid_and_clipping(self):
        f = _facade(facade(els=[{"k": "window", "box": [1, 1, 1, 1], "grid": [5, 2, 2.5, 4]}]), "p")
        boxes = [r for _, r, _ in facade_elements(f)]
        self.assertEqual(len(boxes), 8)   # the fifth column starts at u=11, past the 10 m facade
        self.assertTrue(all(u + w <= 10 and v + h <= 9 for u, v, w, h in boxes))

    def test_ground_openings_are_cut_not_holes(self):
        ps = parts(facade(els=[{"k": "door", "box": [4, 0, 1.2, 2.4]}, {"k": "window", "box": [1, 3, 1, 1.5]}]))
        wall = ps[0]
        self.assertEqual(len(wall["holes"]), 1)
        self.assertEqual(len(wall["cut"]), 1)

    def test_overlapping_openings_merge(self):
        ps = parts(facade(els=[{"k": "window", "box": [1, 1, 2, 2]}, {"k": "window", "box": [2, 2, 2, 2]}]))
        self.assertEqual(ps[0]["holes"], [[1.0, 1.0, 3.0, 3.0]])
        validate({"parts": [ps[0]]})  # the planned wall is itself a valid panel

    def test_touching_openings_merge(self):
        # Two windows sharing an edge (seen in cmp_b0333) must become one hole.
        ps = parts(facade(els=[{"k": "window", "box": [1, 1, 1, 2]}, {"k": "window", "box": [1, 3, 1, 1]}]))
        self.assertEqual(ps[0]["holes"], [[1.0, 1.0, 1.0, 3.0]])

    def test_merge_is_fast_on_stacked_openings(self):
        t = time.time()
        merged = _merge_rects([[i * 0.01, 1, 1, 1] for i in range(1000)])
        self.assertEqual(len(merged), 1)
        self.assertLess(time.time() - t, 2.0)

    def test_projections_and_balcony(self):
        ps = parts(facade(rot=90, els=[{"k": "cornice", "box": [0, 8, 10, 0.5], "d": 0.5},
                                       {"k": "balcony", "box": [2, 3, 3, 1.1], "rail": "solid"}]))
        steps = [p for p in ps if "cornice" in p["name"]]
        self.assertEqual(len(steps), 3)                              # corbelled profile
        self.assertAlmostEqual(sum(p["size"][2] for p in steps), 0.5)
        top = steps[-1]
        self.assertEqual(top["size"][:2], [10.0, 0.5])
        # rot 90: local -y (outward) maps to world +x, so the top step starts 0.5 m out
        self.assertAlmostEqual(top["at"][0], 0.5)
        self.assertEqual(sum("balcony" in p["name"] for p in ps), 4)   # slab, rail, two sides

    def test_arched_openings(self):
        ps = parts(facade(els=[{"k": "window", "box": [1, 1, 1.2, 2.4], "shape": "arch", "bars": [1, 1]},
                               {"k": "door", "box": [4, 0, 1.4, 3], "shape": "seg"}]))
        wall = ps[0]
        self.assertEqual(len(wall["holes"]), 1)
        for got, want in zip(wall["holes"][0], [1.0, 1.0, 1.2, 2.4, 1]):   # 1 = arch
            self.assertAlmostEqual(got, want)
        self.assertEqual(wall["cut"][0]["type"], "prism")             # door on the ground line
        glass = [p for p in ps if "glass" in p["name"]][0]
        self.assertEqual(glass["type"], "prism")
        self.assertGreater(len(glass["pts"]), 4)
        bars = [p for p in ps if "bar" in p["name"]]
        # bars stay below the spring line of the arch
        self.assertTrue(all(b["at"][2] + b["size"][2] <= 1 + 2.4 - 0.6 + 1e-9 for b in bars))
        validate({"parts": [wall]})       # the planned wall is a valid panel with a shaped hole

    def test_pediments(self):
        for shape in ("tri", "seg"):
            ps = parts(facade(els=[{"k": "cornice", "box": [1, 5, 2, 0.6], "shape": shape}]))
            ped = [p for p in ps if "cornice" in p["name"]][0]
            self.assertEqual(ped["type"], "prism")
            self.assertAlmostEqual(max(q[1] for q in ped["pts"]), 5.6)
            self.assertAlmostEqual(min(q[1] for q in ped["pts"]), 5.0)
            validate({"parts": [ped]})

    def test_shape_rules(self):
        for el, msg in (({"k": "window", "box": [1, 1, 1, 1], "shape": "tri"}, ".shape"),
                        ({"k": "sill", "box": [1, 1, 1, 1], "shape": "arch"}, "nothing for sill")):
            with self.assertRaises(SpecError) as cm:
                parts(facade(els=[el]))
            self.assertIn(msg, str(cm.exception))

    def test_volume_behind_the_facade(self):
        ps = parts(facade(depth=12, floors=3, roof="gable", roof_h=4))
        names = [p["name"] for p in ps]
        for n in ("facade side left", "facade side right", "facade back", "facade floor 1",
                  "facade floor 2", "facade roof slab", "facade roof"):
            self.assertIn(n, names)
        roof = ps[names.index("facade roof")]
        self.assertEqual(roof["len"], 10)
        self.assertEqual(roof["pts"][2], [6.0, 4])
        import json
        import rhinospec
        out = json.loads(rhinospec.check(json.dumps({"parts": [facade(depth=12, floors=3, roof="gable")]})))
        self.assertNotIn("floating", out)
        with self.assertRaises(SpecError):
            parts(facade(depth=0.5))      # thinner than two walls

    def test_units_scale_every_detail(self):
        # Found by fuzzing: detail sizes were metres whatever the spec units, so a facade in mm
        # got 0.06 mm frames that Rhino could not build.
        def plan(units, k):
            f = facade(w=10 * k, h=9 * k, depth=8 * k, floors=3, roof="gable", els=[
                {"k": "window", "box": [1 * k, 1 * k, 1 * k, 1.5 * k], "bars": [1, 1]},
                {"k": "window", "box": [4 * k, 1 * k, 1 * k, 2 * k], "shape": "arch"},
                {"k": "balcony", "box": [6 * k, 3 * k, 2 * k, 1.1 * k]},
                {"k": "molding", "box": [0, 8 * k, 10 * k, 0.5 * k], "d": 0.6 * k},
                {"k": "cornice", "box": [1 * k, 3 * k, 1 * k, 0.4 * k], "shape": "tri"}])
            return validate({"units": units, "parts": [f]})["parts"]

        def flat(v):
            return [x for y in v for x in flat(y)] if isinstance(v, list) else [v] if isinstance(v, (int, float)) else []

        in_m, in_mm = plan("m", 1), plan("mm", 1000)
        self.assertEqual([p["name"] for p in in_m], [p["name"] for p in in_mm])
        for a, b in zip(in_m, in_mm):
            for key in ("at", "size", "t", "len", "pts", "holes"):
                if key in a:
                    if key == "holes":   # a 5th value is a shape code, not a length
                        self.assertEqual([h[4:] for h in a[key]], [h[4:] for h in b[key]])
                        va, vb = flat([h[:4] for h in a[key]]), flat([h[:4] for h in b[key]])
                    else:
                        va, vb = flat(a[key]), flat(b[key])
                    for x, y in zip(va, vb):
                        self.assertAlmostEqual(x * 1000, y, places=6, msg="%s %s" % (a["name"], key))

    def test_explicit_positions(self):
        # Uneven rows: a grid step can't follow them, xs/ys can (px, y down -> v up).
        f = _facade(facade(w=None, h=10, px=[0, 0, 100, 100],
                           els=[{"k": "window", "box": [10, 10, 20, 20], "xs": [10, 50], "ys": [10, 34, 70]}]), "p")
        boxes = sorted((round(u, 6), round(v, 6)) for _, (u, v, w, h), _ in facade_elements(f))
        self.assertEqual(len(boxes), 6)
        self.assertEqual(sorted(set(v for _, v in boxes)), [2.0, 5.6, 8.0])   # tops 70, 34, 10 -> v of the bottoms
        self.assertEqual(sorted(set(u for u, _ in boxes)), [1.0, 5.0])
        with self.assertRaises(SpecError):
            parts(facade(els=[{"k": "window", "box": [1, 1, 1, 1], "grid": [2, 1, 2, 0], "xs": [1, 3]}]))

    def test_px_conversion(self):
        f = _facade(facade(w=None, h=10, px=[100, 0, 300, 400],
                           els=[{"k": "window", "box": [120, 200, 140, 260], "grid": [2, 2, 40, 100]}]), "p")
        self.assertAlmostEqual(f["w"], 5.0)
        boxes = sorted(r for _, r, _ in facade_elements(f))
        u, v, w, h = boxes[0]
        self.assertAlmostEqual(u, 0.5)
        self.assertAlmostEqual(w, 0.5)
        self.assertAlmostEqual(h, 1.5)
        self.assertEqual(sorted(round(b[1], 3) for b in boxes), [1.0, 1.0, 3.5, 3.5])  # y down -> v up

    def test_rejections(self):
        for kw, msg in ((dict(els=[{"k": "roof", "box": [0, 0, 1, 1]}]), ".k"),
                        (dict(els=[{"k": "sill", "box": [0, 0, 1, 1], "bars": [1, 1]}]), "glazing"),
                        (dict(els=[{"k": "window", "box": [0, 0, 1, 1], "grid": [40, 40, 1, 1]}]), "elements"),
                        (dict(px=[0, 0, 0, 10]), ".px"),
                        (dict(px=[0, 0, 10, 10], frac=True), "either px or frac"),
                        (dict(px=[0, 0, 10, 10], els=[{"k": "window", "box": [5, 5, 4, 6]}]), "corners"),
                        (dict(els=[]), "non-empty"),
                        (dict(script="x"), "unknown key")):
            with self.assertRaises(SpecError) as cm:
                parts(facade(**kw))
            self.assertIn(msg, str(cm.exception))


XML = ("<object>\r<points>\r<x>\r0.0\r</x>\r<x>\r1.0\r</x>\r<y>\r0.0\r</y>\r<y>\r0.5\r</y>\r</points>\r"
       "<label>\r2\r</label>\r<labelname>\rfacade\r</labelname>\r</object>"
       "<object><points><x>0.1</x><x>0.3</x><y>0.2</y><y>0.25</y></points><labelname>window</labelname></object>"
       "<object><points><x>0.1</x><x>0.3</x><y>0.2</y><y>0.25</y></points><labelname>background</labelname></object>")


class Benchmark(unittest.TestCase):
    def test_cmp_axes_are_swapped(self):
        rect, objs = fb.parse_annotation(XML)
        self.assertEqual(rect, (0.0, 0.0, 0.5, 1.0))           # <y> is horizontal, <x> vertical
        self.assertEqual(objs, [("window", 0.2, 0.1, 0.25, 0.3)])

    def test_annotation_round_trip_scores_one(self):
        rect, objs = fb.parse_annotation(XML)
        gt = fb.annotation_to_spec(rect, objs, 800, 1000, "t")
        f = validate(gt)["parts"]
        self.assertTrue(f)
        s = fb.score(gt, gt)
        self.assertEqual(s["mIoU"], 1.0)
        self.assertEqual(s["openings_IoU"], 1.0)

    def test_disjoint_prediction_scores_zero(self):
        rect, objs = fb.parse_annotation(XML)
        gt = fb.annotation_to_spec(rect, objs, 800, 1000, "t")
        pred = {"parts": [{"type": "facade", "w": 1, "h": 1, "frac": True,
                           "els": [{"k": "door", "box": [0.8, 0.0, 0.1, 0.1]}]}]}
        s = fb.score(gt, pred)
        self.assertEqual(s["per_class"]["window"], 0.0)
        self.assertEqual(s["missed"], ["window"])
        self.assertEqual(s["extra"], ["door"])

    def test_ids_cannot_escape_the_dataset(self):
        for bad in ("../secret", "cmp_b0001/../../x", "cmp_b001", "cmp_b0001\n"):
            with self.assertRaises(SystemExit):
                fb._paths(bad)


if __name__ == "__main__":
    unittest.main()
