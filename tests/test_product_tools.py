"""Pure parts of the product tools (GLB export, clash check, placeholder placement): they run
without Rhino, which only the _run() functions need."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))

from clash_check import allowed_reason, boxes_overlap  # noqa: E402
from export_glb import is_metal_name, srgb_to_linear  # noqa: E402
from place_on_placeholder import choose_normal  # noqa: E402


class ExportGlb(unittest.TestCase):
    def test_srgb_to_linear(self):
        self.assertEqual(srgb_to_linear(0.0), 0.0)
        self.assertAlmostEqual(srgb_to_linear(1.0), 1.0)
        self.assertAlmostEqual(srgb_to_linear(0.5), 0.2140, places=3)
        self.assertAlmostEqual(srgb_to_linear(0.04), 0.04 / 12.92)

    def test_metal_whole_words_only(self):
        self.assertTrue(is_metal_name("MAT_metal_steel_brushed"))
        self.assertTrue(is_metal_name("MAT_tin"))
        self.assertFalse(is_metal_name("MAT_plastic_satin_grey"))   # "satin" contains "tin"
        self.assertFalse(is_metal_name("MAT_rubber_black"))


class ClashCheck(unittest.TestCase):
    def test_boxes(self):
        a = (0, 0, 0, 1, 1, 1)
        self.assertTrue(boxes_overlap(a, (0.5, 0.5, 0.5, 2, 2, 2)))
        self.assertTrue(boxes_overlap(a, (1, 0, 0, 2, 1, 1)))          # touching counts
        self.assertFalse(boxes_overlap(a, (1.1, 0, 0, 2, 1, 1)))

    def test_allowed_either_order(self):
        allowed = [["MP2", "pcb_cliff", "screwed to the chassis"]]
        self.assertEqual(allowed_reason("pcb_cliff", "MP2", allowed), "screwed to the chassis")
        self.assertIsNone(allowed_reason("MP2", "MP3", allowed))


class Placement(unittest.TestCase):
    def test_facing_vector(self):
        self.assertEqual(choose_normal((0, 0, 1), (0, 0, -1), (0, 0, 0)), (0, 0, -1))
        self.assertEqual(choose_normal((0, 0, 1), None, (0, 0, 0)), (0, 0, 1))

    def test_facing_outward(self):
        self.assertEqual(choose_normal((1, 0, 0), "outward", (-170, -20, 40)), (-1, 0, 0))
        self.assertEqual(choose_normal((1, 0, 0), "outward", (170, 5, 40)), (1, 0, 0))


if __name__ == "__main__":
    unittest.main()
