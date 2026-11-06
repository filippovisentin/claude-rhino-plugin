"""Perspective-photo benchmark helpers (no dataset needed)."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "dev"))

import numpy as np  # noqa: E402

import photo_bench as pb  # noqa: E402
import rectify as rc  # noqa: E402


class BackProjection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.old = pb.WORK
        pb.WORK = self.tmp

    def tearDown(self):
        pb.WORK = self.old

    def pred(self, box):
        return {"parts": [{"type": "facade", "h": 5, "px": [0, 0, 100, 100], "els": [{"k": "window", "box": box}]}]}

    def test_without_rectification_boxes_stay_put(self):
        (k, quad), = pb.pred_quads(self.pred([10, 20, 30, 40]), "x1")
        self.assertEqual(quad, [(10, 20), (30, 20), (30, 40), (10, 40)])

    def test_boxes_read_on_the_straightened_photo_go_back_to_the_original(self):
        corners = [(60, 30), (380, 70), (370, 270), (50, 300)]
        with open(os.path.join(self.tmp, "x2.rect.json"), "w") as fh:
            json.dump({"corners": corners, "size": [300, 200], "ratio": 1.5}, fh)
        (k, quad), = pb.pred_quads(self.pred([0, 0, 300, 200]), "x2")
        for (x, y), (cx, cy) in zip(quad, corners):     # the full rectified frame maps onto the corners
            self.assertAlmostEqual(x, cx, places=6)
            self.assertAlmostEqual(y, cy, places=6)

    def test_grids_expand_before_projection(self):
        pred = {"parts": [{"type": "facade", "h": 5, "px": [0, 0, 100, 100],
                           "els": [{"k": "window", "box": [0, 0, 10, 10], "grid": [3, 2, 20, 30]}]}]}
        self.assertEqual(len(pb.pred_quads(pred, "x3")), 6)

    def test_block_faces_use_their_own_straightening(self):
        corners = [(60, 30), (380, 70), (370, 270), (50, 300)]
        with open(os.path.join(self.tmp, "x4.right.rect.json"), "w") as fh:
            json.dump({"corners": corners, "size": [300, 200], "ratio": 1.5}, fh)
        el = lambda box: {"px": [0, 0, 300, 200], "els": [{"k": "window", "box": box}]}
        pred = {"parts": [{"type": "block", "w": 9, "d": 6, "h": 5, "faces": {
            "front": el([10, 20, 30, 40]), "right": el([0, 0, 300, 200]), "left": {"els": []}}}]}
        (_, front), (_, right) = pb.pred_quads(pred, "x4")
        self.assertEqual(front, [(10, 20), (30, 20), (30, 40), (10, 40)])   # read on the photo itself
        for (x, y), (cx, cy) in zip(right, corners):
            self.assertAlmostEqual(x, cx, places=6)
            self.assertAlmostEqual(y, cy, places=6)


class Hznu(unittest.TestCase):
    def test_polygons_in_either_layout(self):
        labelme_style = {"shapes": [{"label": "window", "points": [[0, 0], [4, 0], [4, 3]]},
                                    {"label": "door", "points": [[5, 5], [6, 5], [6, 8], [5, 8]]},
                                    {"label": "tree", "points": [[1, 1], [2, 2], [1, 2]]}]}
        coco_style = {"annotations": [{"category": "windows", "segmentation": [0, 0, 4, 0, 4, 3]}]}
        self.assertEqual(len(pb.hznu_polygons(labelme_style, "window")), 1)
        self.assertEqual(len(pb.hznu_polygons(labelme_style, "door")), 1)
        self.assertEqual(pb.hznu_polygons(coco_style, "window"), [[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0)]])


class Ids(unittest.TestCase):
    def test_ids_cannot_escape(self):
        for bad in ("../x", "a/b", "a\\b", "x" * 200, ""):
            with self.assertRaises(SystemExit):
                pb._id(bad)


if __name__ == "__main__":
    unittest.main()
