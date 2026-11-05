"""Finials and urns: they stand on a parapet or a cornice, above the eaves when on the wall top."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "rhino"))
sys.path.insert(0, os.path.dirname(__file__))

from rhinospec import SpecError, check, validate  # noqa: E402
from rhinospec.checks import bbox  # noqa: E402
from rhinospec.naming import layer_path  # noqa: E402
from test_block import connected_groups  # noqa: E402

T = 0.4


def facade(els, **kw):
    return dict({"type": "facade", "name": "F", "w": 12, "h": 10, "t": T, "els": els}, **kw)


def parts(els, **kw):
    return validate({"units": "m", "layer": "L", "parts": [facade(els, **kw)]})["parts"]


def finials(ps):
    return [p for p in ps if p.get("cat") == "finials"]


class Finial(unittest.TestCase):
    def test_finials_on_the_parapet_rise_above_the_eaves(self):
        ps = parts([{"k": "finial", "box": [1, 10, 0.5, 1.4], "grid": [3, 1, 4.75, 0]}])
        fs = finials(ps)
        self.assertTrue(fs)
        tops = sorted(set(round(bbox(p)[5], 6) for p in fs))
        self.assertAlmostEqual(tops[-1], 11.4)                          # not clipped at the eaves
        self.assertAlmostEqual(min(bbox(p)[2] for p in fs), 10.0)       # standing on the wall top
        for p in fs:                                                    # over the wall, not in front of it
            b = bbox(p)
            self.assertGreaterEqual(b[1], -1e-9, p["name"])
            self.assertLessEqual(b[4], T + 1e-9, p["name"])
        self.assertEqual(len(set(p["join"] for p in fs)), 3)            # one join group per finial
        out = json.loads(check({"units": "m", "parts": [facade([{"k": "finial", "box": [1, 10, 0.5, 1.4]}])]}))
        self.assertTrue(out["ok"])
        self.assertNotIn("notes", out)
        self.assertNotIn("floating", out)

    def test_shapes(self):
        kinds = {}
        for shape in ("urn", "ball", "spire"):
            ps = finials(parts([{"k": "finial", "box": [5, 10, 0.6, 1.5], "shape": shape}]))
            kinds[shape] = set(p["type"] for p in ps)
            self.assertIn("box", kinds[shape], shape)                   # every finial has its pedestal
            self.assertEqual(connected_groups(ps), 1, shape)
            for p in ps:                                                # inside the read box
                b = bbox(p)
                self.assertTrue(b[0] >= 5 - 1e-9 and b[3] <= 5.6 + 1e-9 and b[5] <= 11.5 + 1e-9, (shape, p["name"], b))
        self.assertIn("revolve", kinds["urn"])
        self.assertIn("sphere", kinds["ball"])
        self.assertIn("cone", kinds["spire"])
        default = finials(parts([{"k": "finial", "box": [5, 10, 0.6, 1.5]}]))
        self.assertIn("revolve", set(p["type"] for p in default))      # urn by default

    def test_finial_on_a_cornice_stands_against_the_wall(self):
        ps = parts([{"k": "cornice", "box": [0, 6, 12, 0.4]}, {"k": "finial", "box": [3, 6.4, 0.4, 1]}])
        fs = finials(ps)
        self.assertTrue(fs)
        self.assertAlmostEqual(max(bbox(p)[4] for p in fs), 0.0)        # touches the wall face
        self.assertTrue(all(bbox(p)[1] < 0 for p in fs))                # in front of it
        self.assertEqual(connected_groups(ps), 1)

    def test_finial_floating_above_the_wall_is_dropped_and_reported(self):
        els = [{"k": "finial", "box": [3, 12, 0.5, 1]}]
        self.assertFalse(finials(parts(els)))
        out = json.loads(check({"units": "m", "parts": [facade(els + [{"k": "window", "box": [1, 1, 1, 1]}])]}))
        self.assertIn("1 element(s) outside", out["notes"][0])

    def test_finial_on_a_gable_slope(self):
        # The apex is at 14 m; the slopes under a 40 cm base are at 13.87 m.
        fs = finials(parts([{"k": "finial", "box": [5.8, 13.8, 0.4, 1]}], top=[[6, 14]]))
        self.assertAlmostEqual(max(bbox(p)[5] for p in fs), 14.8)

    def test_layers_palette_and_colour(self):
        ps = parts([{"k": "finial", "box": [1, 10, 0.5, 1.4]}], palette={"trim": "#aa0000"})
        self.assertTrue(all(p["color"] == "#aa0000" for p in finials(ps)))
        paths = set("::".join(layer_path("L", p, "it")) for p in finials(ps))
        self.assertEqual(paths, {"L::F::Pinnacoli"})
        own = parts([{"k": "finial", "box": [1, 10, 0.5, 1.4], "color": "#123456"}])
        self.assertTrue(all(p["color"] == "#123456" for p in finials(own)))

    def test_rejects(self):
        with self.assertRaises(SpecError) as e:
            parts([{"k": "finial", "box": [1, 10, 0.5, 1.4], "shape": "round"}])
        self.assertIn("urn", str(e.exception))
        with self.assertRaises(SpecError):
            parts([{"k": "finial", "box": [1, 10, 0.5, 1.4], "bars": [1, 1]}])


if __name__ == "__main__":
    unittest.main()
