"""Training data conversion (tools/train_data.py): pure parts, no dataset or GPU needed."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools", "dev"))
import train_data as TD  # noqa: E402

VOC = """<annotation><size><width>1000</width><height>500</height><depth>3</depth></size>
<object><name>fronton-partido</name><bndbox><xmin>100</xmin><ymin>50</ymin><xmax>900</xmax><ymax>150</ymax></bndbox></object>
<object><name>vano-adintelado</name><bndbox><xmin>300</xmin><ymin>200</ymin><xmax>500</xmax><ymax>480</ymax></bndbox></object>
<object><name>Ojo-de-Buey</name><bndbox><xmin>450</xmin><ymin>60</ymin><xmax>550</xmax><ymax>110</ymax></bndbox></object>
<object><name>gargola</name><bndbox><xmin>0</xmin><ymin>0</ymin><xmax>10</xmax><ymax>10</ymax></bndbox></object>
</annotation>"""


class Conversion(unittest.TestCase):
    def test_every_monumai_label_is_mapped(self):
        # the fifteen labels found in the dataset's annotations
        seen = ["vano-adintelado", "arco-apuntado", "arco-medio-punto", "fronton", "arco-herradura", "fronton-partido",
                "pinaculo-gotico", "fronton-curvo", "arco-conopial", "columna-salomonica", "ojo-de-buey",
                "arco-trilobulado", "arco-lobulado", "dintel-adovelado", "serliana"]
        self.assertEqual(sorted(seen), sorted(TD.MONUMAI))
        for k in TD.MONUMAI.values():
            self.assertTrue(k is None or k in TD.PARTS, k)

    def test_voc_objects(self):
        w, h, objs, unknown = TD.voc_objects(VOC)
        self.assertEqual((w, h), (1000, 500))
        self.assertEqual(unknown, ["gargola"])
        self.assertEqual([o[0] for o in objs], ["pediment", "oculus"])      # lintelled opening: left to the teacher
        self.assertEqual(objs[0][1:], (0.1, 0.1, 0.9, 0.3))

    def test_lines(self):
        self.assertEqual(TD.box_line(3, 0.1, 0.2, 0.3, 0.6), "3 0.200000 0.400000 0.200000 0.400000")
        self.assertEqual(TD.box_line(0, -0.2, 0.5, 0.2, 1.4), "0 0.100000 0.750000 0.200000 0.500000")   # clipped
        self.assertIsNone(TD.box_line(0, 0.5, 0.5, 0.5, 0.9))
        self.assertEqual(TD.poly_line(2, [(0, 0), (1.2, 0), (0.5, 0.5)]), "2 0.000000 0.000000 1.000000 0.000000 0.500000 0.500000")
        self.assertIsNone(TD.poly_line(2, [(0, 0), (1, 1)]))

    def test_teacher_fills_only_missing_classes(self):
        objs = [("window", 0.1, 0.1, 0.2, 0.3)]
        guesses = [("window", 0.9, 0.5, 0.1, 0.6, 0.3),     # windows are labelled by the source: ignored
                   ("sill", 0.8, 0.1, 0.3, 0.2, 0.32),      # missing class, confident: added
                   ("sill", 0.3, 0.5, 0.3, 0.6, 0.32),      # not confident enough
                   ("cornice", 0.7, 0.0, 0.0, 1.0, 0.05),
                   ("cornice", 0.6, 0.0, 0.0, 1.0, 0.055)]  # a duplicate of the one just added
        out = TD.fill_missing(objs, guesses, {"window", "door"})
        self.assertEqual([o[0] for o in out], ["window", "sill", "cornice"])

    def test_split_is_stable_per_photo(self):
        ids = ["a%04d" % i for i in range(2000)]
        s = TD.split_ids(ids, fixed_test=["a0007", "a1500"])
        self.assertIn("a0007", s["test"])
        self.assertIn("a1500", s["test"])
        self.assertAlmostEqual(len(s["test"]) / 2000.0, 0.1, delta=0.02)
        self.assertAlmostEqual(len(s["val"]) / 2000.0, 0.1, delta=0.02)
        self.assertEqual(sorted(s["train"] + s["val"] + s["test"]), ids)
        # adding a whole new source moves no existing photo to another split
        more = TD.split_ids(ids + ["b%04d" % i for i in range(3000)], fixed_test=["a0007", "a1500"])
        for k in ("train", "val", "test"):
            self.assertEqual([i for i in more[k] if i.startswith("a")], s[k])

    def test_style_to_spec(self):
        self.assertEqual(TD.spec_style("Baroque architecture"), "classic")
        self.assertEqual(TD.spec_style("Deconstructivism"), "modern")
        self.assertEqual(TD.spec_style("International style"), "modern")
        self.assertEqual(TD.spec_style("Ancient Egyptian architecture"), "plain")

    @unittest.skipUnless(__import__("importlib").util.find_spec("cv2"), "needs OpenCV (detector environment)")
    def test_mask_polygons(self):
        import numpy as np
        m = np.zeros((100, 200), bool)
        m[10:50, 20:120] = True          # one block
        m[80:81, 0:2] = True             # a speck: dropped
        polys = TD.mask_polygons(m)
        self.assertEqual(len(polys), 1)
        xs, ys = [p[0] for p in polys[0]], [p[1] for p in polys[0]]
        self.assertAlmostEqual(min(xs), 0.1, places=2)
        self.assertAlmostEqual(max(xs), 119 / 200.0, places=2)
        self.assertAlmostEqual(min(ys), 0.1, places=2)

    @unittest.skipUnless(__import__("importlib").util.find_spec("cv2"), "needs OpenCV (detector environment)")
    def test_oxford_instances_take_their_class_from_the_semantic_mask(self):
        import numpy as np
        sem = np.zeros((100, 200, 3), np.uint8)
        inst = np.zeros((100, 200, 3), np.uint8)
        sem[:, :] = (255, 255, 0)                                   # facade everywhere: not an object
        for x0, colour in ((20, (10, 20, 30)), (60, (40, 50, 60))):  # two touching windows, two instances
            sem[10:40, x0:x0 + 40] = (255, 0, 0)
            inst[10:40, x0:x0 + 40] = colour
        sem[60:100, 150:180] = (255, 128, 0)                        # a door
        inst[60:100, 150:180] = (70, 80, 90)
        sem[60:62, 150:152] = (255, 0, 0)                           # a few stray window pixels inside it
        sem[70:80, 20:60] = (128, 0, 255)                           # a balcony with no instance (as in the data)
        boxes = sorted(TD.instance_boxes(sem, inst))
        self.assertEqual([b[0] for b in boxes], ["balcony", "door", "window", "window"])
        self.assertEqual(boxes[0][1:], (0.1, 0.7, 0.3, 0.8))
        boxes = boxes[1:]
        self.assertEqual(boxes[1][1:], (0.1, 0.1, 0.3, 0.4))
        self.assertEqual(boxes[2][1:], (0.3, 0.1, 0.5, 0.4))
        self.assertEqual(boxes[0][1:], (0.75, 0.6, 0.9, 1.0))

    def test_tmbud_colours_are_rgb_not_the_readme_bgr(self):
        self.assertEqual(TD.TMBUD[(0, 0, 255)], "sky")             # checked on the masks: top of the frame
        self.assertEqual(TD.TMBUD_PARTS[(255, 255, 0)], "window")
        self.assertNotIn((255, 0, 0), TD.TMBUD)                     # occluders ("noise") stay unlabelled

    def test_scene_and_parts_vocabularies(self):
        self.assertEqual(set(TD.LABELME.values()) | set(TD.HZNU_SCENE.values()) | set(TD.COCO_SCENE.values()),
                         set(TD.SCENE))
        self.assertEqual(TD.PARTS[:10], TD.FY.NAMES)        # yesterday's classes keep their indices
        taught = [c for _, cs in TD.TEACHERS for c in cs]           # each class has exactly one teacher
        self.assertEqual(sorted(taught), sorted(TD.FY.NAMES + sorted(TD.NEW)))
        for src, ks in TD.LABELLED.items():
            self.assertTrue(ks <= set(TD.PARTS), src)


if __name__ == "__main__":
    unittest.main()
