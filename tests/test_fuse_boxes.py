"""Fusion of several detectors' boxes (facade_detect.fuse_boxes) and the mAP50 used to measure it."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import facade_detect as FY  # noqa: E402
import ensemble_report as ER  # noqa: E402


class Fuse(unittest.TestCase):
    def test_agreeing_boxes_merge_into_a_confidence_weighted_average(self):
        out = FY.fuse_boxes([[("window", 0.9, 100, 100, 200, 300)], [("window", 0.3, 110, 100, 210, 300)]],
                            [1, 1], mode="max")
        self.assertEqual(len(out), 1)
        k, c, x0, y0, x1, y1 = out[0]
        self.assertEqual(k, "window")
        self.assertAlmostEqual(c, 0.9)
        self.assertAlmostEqual(x0, 102.5)   # (0.9 * 100 + 0.3 * 110) / 1.2
        self.assertAlmostEqual(x1, 202.5)

    def test_classes_and_distant_boxes_stay_apart(self):
        out = FY.fuse_boxes([[("window", 0.9, 0, 0, 100, 100), ("door", 0.8, 0, 0, 100, 100)],
                             [("window", 0.7, 500, 500, 600, 600)]], [1, 1], mode="max")
        self.assertEqual(sorted(d[0] for d in out), ["door", "window", "window"])

    def test_max_keeps_a_lone_box_of_the_main_model_and_halves_the_second_models(self):
        out = dict((d[0], d[1]) for d in FY.fuse_boxes(
            [[("window", 0.6, 0, 0, 100, 100)], [("door", 0.6, 300, 0, 400, 200)]], [2, 1], mode="max"))
        self.assertAlmostEqual(out["window"], 0.6)
        self.assertAlmostEqual(out["door"], 0.3)

    def test_avg_needs_every_model_to_agree(self):
        lone = FY.fuse_boxes([[("window", 0.8, 0, 0, 100, 100)], []], [1, 1])
        both = FY.fuse_boxes([[("window", 0.8, 0, 0, 100, 100)], [("window", 0.8, 0, 0, 100, 100)]], [1, 1])
        self.assertAlmostEqual(lone[0][1], 0.4)
        self.assertAlmostEqual(both[0][1], 0.8)


class Px(unittest.TestCase):
    def test_px_is_the_box_around_the_elements(self):
        els = [{"k": "window", "box": [100, 200, 150, 260]}, {"k": "cornice", "box": [40, 80, 700, 110]},
               {"k": "door", "box": [300, 400, 360, 520]}]
        self.assertEqual(FY.facade_px(els, 768, 569), [40, 80, 700, 520])

    def test_no_elements_keep_the_whole_photo(self):
        self.assertEqual(FY.facade_px([], 768, 569), [0, 0, 768, 569])


class AP(unittest.TestCase):
    def test_perfect_and_empty(self):
        gts = {"a": [[0, 0, 10, 10]], "b": [[0, 0, 10, 10]]}
        self.assertAlmostEqual(ER.ap50([(0.9, "a", [0, 0, 10, 10]), (0.8, "b", [0, 0, 10, 10])], gts), 1.0)
        self.assertEqual(ER.ap50([], gts), 0.0)
        self.assertIsNone(ER.ap50([], {"a": []}))

    def test_a_confident_false_positive_costs_precision(self):
        gts = {"a": [[0, 0, 10, 10]]}
        good = ER.ap50([(0.9, "a", [0, 0, 10, 10]), (0.1, "a", [50, 50, 60, 60])], gts)
        bad = ER.ap50([(0.9, "a", [50, 50, 60, 60]), (0.1, "a", [0, 0, 10, 10])], gts)
        self.assertAlmostEqual(good, 1.0)
        self.assertAlmostEqual(bad, 0.5)

    def test_one_prediction_matches_one_object(self):
        gts = {"a": [[0, 0, 10, 10], [0, 0, 10, 10]]}
        self.assertAlmostEqual(ER.ap50([(0.9, "a", [0, 0, 10, 10])], gts), 51 / 101.0)


if __name__ == "__main__":
    unittest.main()
