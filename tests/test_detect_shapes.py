"""Detector classes beyond CMP's (arch, oculus, pediments, finial) -> the spec's own words."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import facade_yolo as FY  # noqa: E402

W, H = 1000, 800


def els(dets):
    return FY.draft_elements(dets, W, H, conf=0.25)


def find(es, k, shape=None):
    return [e for e in es if e["k"] == k and (shape is None or e.get("shape") == shape)]


class Shapes(unittest.TestCase):
    def test_arch_and_oculus_shape_the_opening_under_them(self):
        es = els([("window", 0.9, 100, 300, 200, 500), ("arch", 0.8, 98, 295, 202, 505),
                  ("door", 0.8, 400, 500, 520, 800), ("arch", 0.7, 395, 490, 525, 800),
                  ("window", 0.9, 700, 100, 760, 160), ("oculus", 0.8, 702, 102, 758, 158)])
        self.assertEqual(find(es, "window", "arch")[0]["box"], [100, 300, 200, 500])   # the window's own box
        self.assertEqual(len(find(es, "door", "arch")), 1)
        self.assertEqual(len(find(es, "window", "round")), 1)
        self.assertEqual(len(es), 3)                                    # no extra element for the shapes

    def test_lone_arch_or_oculus_becomes_an_opening_of_that_shape(self):
        es = els([("arch", 0.8, 100, 300, 200, 500), ("oculus", 0.7, 700, 100, 760, 160)])
        self.assertEqual(find(es, "window", "arch")[0]["box"], [100, 300, 200, 500])
        self.assertEqual(len(find(es, "window", "round")), 1)

    def test_pediments(self):
        es = els([("window", 0.9, 100, 300, 200, 500),
                  ("pediment", 0.8, 90, 250, 210, 298),        # small, just above the window: its hood
                  ("pediment", 0.8, 300, 20, 700, 150),        # wide, over nothing: a temple pediment
                  ("pediment_seg", 0.7, 600, 400, 700, 440)])  # segmental: a curved hood
        self.assertEqual(find(es, "cornice", "tri")[0]["box"], [90, 250, 210, 298])
        self.assertEqual(find(es, "pediment")[0]["box"], [300, 20, 700, 150])
        self.assertEqual(len(find(es, "cornice", "seg")), 1)

    def test_finial_and_confidence(self):
        es = els([("finial", 0.8, 10, 10, 40, 90), ("arch", 0.1, 100, 300, 200, 500)])
        self.assertEqual(find(es, "finial", "spire")[0]["box"], [10, 10, 40, 90])
        self.assertFalse(find(es, "window"))                           # below the confidence

    def test_cmp_classes_unchanged_and_ordered(self):
        dets = [("sill", 0.8, 100, 500, 200, 520), ("window", 0.9, 100, 300, 200, 500),
                ("window", 0.85, 102, 302, 198, 498)]                  # a duplicate: dropped
        es = els(dets)
        self.assertEqual([e["k"] for e in es], ["window", "sill"])
        self.assertNotIn("shape", es[0])


if __name__ == "__main__":
    unittest.main()
