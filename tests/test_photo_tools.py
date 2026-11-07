"""overlay and crop on any photo (tools/photo_tools.py), the runtime versions of facade_bench's."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None
if Image is not None:
    import photo_tools as PT  # noqa: E402  (a missing module must fail, not skip)
else:  # pragma: no cover
    PT = None

SPEC = {"parts": [{"type": "facade", "h": 10, "px": [20, 20, 380, 280],
                   "els": [{"k": "window", "box": [50, 50, 90, 110], "grid": [2, 1, 100, 0]}]}]}


@unittest.skipIf(PT is None, "needs Pillow")
class Tools(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.photo = os.path.join(self.dir, "photo.jpg")
        Image.new("RGB", (400, 300), (200, 190, 170)).save(self.photo)

    def test_crop_enlarges_and_reports_origin_and_scale(self):
        out = os.path.join(self.dir, "crop.jpg")
        r = PT.crop(self.photo, [100, 50, 200, 150], out)
        self.assertEqual(r, {"origin": [100, 50], "scale": 7.68})
        with Image.open(out) as im:
            self.assertEqual(max(im.size), 768)

    def test_crop_refuses_bad_boxes_and_writes_nothing(self):
        for box in ([200, 50, 100, 150], [100, 50, 500, 150], [-5, 0, 10, 10]):
            out = os.path.join(self.dir, "bad.jpg")
            with self.assertRaises(ValueError):
                PT.crop(self.photo, box, out)
            self.assertFalse(os.path.exists(out))

    def test_overlay_keeps_the_photo_size_and_draws_every_grid_box(self):
        spec = os.path.join(self.dir, "spec.json")
        with open(spec, "w") as fh:
            json.dump(SPEC, fh)
        out = os.path.join(self.dir, "over.jpg")
        n = PT.overlay(self.photo, spec, out)
        self.assertEqual(n, 2)
        with Image.open(out) as im:
            self.assertEqual(im.size, (400, 300))
            self.assertNotEqual(im.getpixel((50, 80)), (200, 190, 170))

    def test_overlay_takes_a_detector_draft_too(self):
        draft = os.path.join(self.dir, "draft.json")
        with open(draft, "w") as fh:
            json.dump({"img": [400, 300], "px": [20, 20, 380, 280], "els": [{"k": "door", "box": [10, 10, 40, 60]}]}, fh)
        self.assertEqual(PT.overlay(self.photo, draft, os.path.join(self.dir, "o.jpg")), 1)

    def test_overlay_takes_a_block_face(self):
        # a whole building: the front by default, any other px face with --face
        block = {"parts": [{"type": "block", "w": 12, "d": 10, "h": 10, "faces": {
            "front": {"px": [20, 20, 380, 280], "els": [{"k": "window", "box": [50, 50, 90, 110], "grid": [3, 1, 100, 0]}]},
            "right": {"px": [0, 0, 400, 300], "els": [{"k": "door", "box": [10, 200, 60, 300]}]},
            "back": {"els": []}}}]}
        spec = os.path.join(self.dir, "block.json")
        with open(spec, "w") as fh:
            json.dump(block, fh)
        self.assertEqual(PT.overlay(self.photo, spec, os.path.join(self.dir, "b.jpg")), 3)
        self.assertEqual(PT.overlay(self.photo, spec, os.path.join(self.dir, "r.jpg"), face="right"), 1)
        for bad in ("back", "top"):
            with self.assertRaises(ValueError):
                PT.overlay(self.photo, spec, os.path.join(self.dir, "x.jpg"), face=bad)
        p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "photo_tools.py"), "overlay", self.photo,
                            spec, os.path.join(self.dir, "c.jpg"), "--face", "right"], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        self.assertEqual(json.loads(p.stdout)["boxes"], 1)

    def test_command_line_prints_the_crop_json(self):
        out = os.path.join(self.dir, "c.jpg")
        p = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "photo_tools.py"), "crop", self.photo,
                            "100", "50", "200", "150", out], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        self.assertEqual(json.loads(p.stdout), {"origin": [100, 50], "scale": 7.68})


if __name__ == "__main__":
    unittest.main()
