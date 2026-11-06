"""Tests for the build sanity checks, the photo refiner and pixel-space scoring (no Rhino, no dataset)."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "rhino"))
sys.path.insert(0, os.path.join(HERE, "..", "tools"))
sys.path.insert(0, os.path.join(HERE, "..", "tools", "dev"))

import numpy as np  # noqa: E402

import rhinospec  # noqa: E402
from rhinospec import checks, validate  # noqa: E402
import facade_bench as fb  # noqa: E402
import facade_refine as fr  # noqa: E402


def table(leg_h):
    return {"units": "m", "parts": [
        {"type": "box", "name": "top", "at": [0, 0, 0.72], "size": [1.6, 0.8, 0.04]},
        {"type": "array", "of": {"type": "box", "name": "leg", "at": [0.05, 0.05, 0], "size": [0.05, 0.05, leg_h]},
         "n": [2, 2, 1], "step": [1.45, 0.65, 0]}]}


class Checks(unittest.TestCase):
    def test_table_ok_and_floating(self):
        self.assertNotIn("floating", json.loads(rhinospec.check(json.dumps(table(0.72)))))
        out = json.loads(rhinospec.check(json.dumps(table(0.6))))
        self.assertEqual(out["floating"], 1)
        self.assertEqual(out["floating_examples"], ["top"])

    def test_rotated_box_bbox(self):
        p = validate({"parts": [{"type": "box", "size": [2, 1, 1], "rot": 90}]})["parts"][0]
        x0, y0, z0, x1, y1, z1 = checks.bbox(p)
        self.assertAlmostEqual(x0, -1)
        self.assertAlmostEqual(y1, 2)

    def test_every_primitive_has_a_bbox(self):
        sq = [[0, 0], [1, 0], [1, 1], [0, 1]]
        ps = validate({"parts": [
            {"type": "cyl", "r": 1, "h": 1}, {"type": "cone", "r": 1, "h": 1}, {"type": "sphere", "r": 1},
            {"type": "torus", "R": 2, "r": 0.5}, {"type": "extrude", "pts": sq, "h": 1},
            {"type": "prism", "pts": [[0, 0], [1, 0], [0, 1]], "len": 1},
            {"type": "revolve", "profile": [[0, 0], [1, 1]]},
            {"type": "loft", "sections": [{"pts": sq, "z": 0}, {"pts": sq, "z": 1}]},
            {"type": "pipe", "path": [[0, 0, 0], [0, 0, 1]], "r": 0.1},
            {"type": "panel", "size": [2, 2], "t": 0.2}]})["parts"]
        for p in ps:
            b = checks.bbox(p)
            self.assertTrue(all(b[i] <= b[i + 3] for i in range(3)), p["type"])

    def test_facades_do_not_float(self):
        spec = {"parts": [{"type": "facade", "w": 10, "h": 9, "els": [
            {"k": "window", "box": [1, 1, 1, 1.5], "grid": [4, 3, 2.2, 3], "bars": [1, 1]},
            {"k": "balcony", "box": [0.5, 3, 4, 1.1]}, {"k": "cornice", "box": [0, 8.5, 10, 0.5]}]}]}
        self.assertNotIn("floating", json.loads(rhinospec.check(json.dumps(spec))))

    def test_huge_models_are_skipped_not_stalled(self):
        parts = [{"type": "sphere", "at": [i * 3.0, 0, 5], "r": 1.0, "rot": 0.0} for i in range(1500)]
        labels, skipped = checks.floating(parts)
        self.assertTrue(skipped)


def synthetic_facade():
    """A 200x300 grey wall with a 3x4 grid of dark windows; one window is missing from the spec."""
    img = np.full((300, 200), 180.0)
    boxes = []
    for j in range(4):
        for i in range(3):
            x0, y0 = 20 + i * 60, 20 + j * 70
            img[y0:y0 + 40, x0:x0 + 30] = 40.0
            img[y0 + 18:y0 + 22, x0:x0 + 30] = 220.0   # a glazing bar, so windows have texture
            boxes.append([x0, y0, x0 + 30, y0 + 40])
    return img, boxes


class Refine(unittest.TestCase):
    def test_find_recovers_aligned_copies(self):
        img, boxes = synthetic_facade()
        spec = {"parts": [{"type": "facade", "h": 12, "px": [0, 0, 200, 300],
                           "els": [{"k": "window", "box": b} for b in boxes[:-1]]}]}
        new, stats = fr.refine(spec, img, find=("window",), thr=0.6)
        self.assertEqual(stats["added"], 1)
        found = new["parts"][0]["els"][-1]["box"]
        self.assertGreater(fr.iou(found, boxes[-1]), 0.9)
        json.dumps(new)   # numpy ints must not leak into the output
        validate(new)

    def test_unaligned_lookalikes_are_rejected(self):
        img, boxes = synthetic_facade()
        img[250:290, 5:35] = 40.0        # a window-like patch off every row and column
        spec = {"parts": [{"type": "facade", "h": 12, "px": [0, 0, 200, 300],
                           "els": [{"k": "window", "box": boxes[0]}]}]}
        _, stats = fr.refine(spec, img, find=("window",), thr=0.6)
        # copies in row 0 and column 0 are fine; the stray patch must not be among them
        self.assertTrue(all(not (b[0] < 35 and b[1] > 240) for b in
                            [e["box"] for e in fr.refine(spec, img)[0]["parts"][0]["els"]]))
        self.assertGreaterEqual(stats["added"], 2)

    def test_snap_moves_edges_onto_the_window(self):
        img, boxes = synthetic_facade()
        gx, gy = fr.gradients(img)
        x0, y0, x1, y1 = boxes[4]
        snapped = fr.snap_box([x0 + 3, y0 - 3, x1 + 2, y1 + 3], gx, gy)
        self.assertGreater(fr.iou(snapped, boxes[4]), 0.9)

    def test_needs_a_px_facade(self):
        with self.assertRaises(ValueError):
            fr.refine({"parts": [{"type": "facade", "w": 1, "h": 1, "els": []}]}, np.zeros((5, 5)))


class PixelScore(unittest.TestCase):
    def test_image_masks_agree_with_themselves(self):
        objs = [("window", 0.1, 0.1, 0.2, 0.3)]
        g, p = fb.image_masks(objs, [("window", [10, 20, 20, 60])], 100, 200)
        self.assertEqual(g["window"], p["window"])

    def test_px_boxes_expand_grids(self):
        spec = {"parts": [{"type": "facade", "h": 10, "px": [0, 0, 100, 100],
                           "els": [{"k": "window", "box": [10, 10, 20, 30], "grid": [2, 2, 40, 50]}]}]}
        boxes = fb.px_boxes(spec)
        self.assertEqual(len(boxes), 4)
        self.assertEqual(boxes[-1], ("window", [50, 60, 60, 80]))


if __name__ == "__main__":
    unittest.main()


class TiltAndTurn(unittest.TestCase):
    def test_tilt_stands_a_torus_up(self):
        p = validate({"parts": [{"type": "torus", "R": 9.2, "r": 1.2, "tilt": [90, 0], "at": [0, 0, 10.4]}]})["parts"][0]
        x0, y0, z0, x1, y1, z1 = checks.bbox(p)
        self.assertAlmostEqual(z0, 0, places=6)
        self.assertAlmostEqual(z1, 20.8, places=6)
        self.assertAlmostEqual(y1 - y0, 2.4, places=6)

    def test_tilt_lays_a_cylinder_down(self):
        p = validate({"parts": [{"type": "cyl", "r": 0.5, "h": 4, "tilt": [0, 90]}]})["parts"][0]
        x0, y0, z0, x1, y1, z1 = checks.bbox(p)
        self.assertAlmostEqual(x1 - x0, 4, places=6)     # the axis now runs along x
        self.assertAlmostEqual(z1 - z0, 1, places=6)

    def test_turn_makes_a_spiral(self):
        parts = validate({"parts": [{"type": "array", "of": {"type": "box", "at": [0, -0.1, 0], "size": [1, 0.2, 0.04]},
                                     "n": [1, 1, 12], "step": [0, 0, 0.18], "turn": 30}]})["parts"]
        self.assertEqual([round(p["rot"]) for p in parts[:4]], [0, 30, 60, 90])
        self.assertAlmostEqual(parts[3]["at"][0], 0.1)     # (0, -0.1) turned 90 degrees
        self.assertAlmostEqual(parts[3]["at"][1], 0.0)
        self.assertAlmostEqual(parts[-1]["at"][2], 11 * 0.18)
        self.assertTrue(all(-360 <= p["rot"] <= 360 for p in parts))

    def test_pipe_path_follows_at(self):
        p = validate({"parts": [{"type": "pipe", "at": [10, 0, 0], "path": [[0, 0, 0], [0, 0, 2]], "r": 0.1}]})["parts"][0]
        self.assertAlmostEqual(checks.bbox(p)[0], 9.9)

    def test_bad_tilt_and_turn(self):
        from rhinospec import SpecError
        for part in ({"type": "box", "size": [1, 1, 1], "tilt": [90]},
                     {"type": "array", "of": {"type": "sphere", "r": 1}, "n": [2, 1, 1], "step": [1, 0, 0], "turn": 400}):
            with self.assertRaises(SpecError):
                validate({"parts": [part]})
