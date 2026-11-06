"""The runtime detector (tools/facade_detect.py) stands alone: the plugin runs it on studio PCs,
where the benchmark and its datasets do not exist."""
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")


class Standalone(unittest.TestCase):
    def test_imports_without_the_benchmark(self):
        code = "import sys; sys.path.insert(0, %r); import facade_detect; print('facade_bench' in sys.modules)" % TOOLS
        p = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        self.assertEqual(p.stdout.strip(), "False")

    def test_detection_api(self):
        sys.path.insert(0, TOOLS)
        import facade_detect as FD
        for name in ("pick_device", "fuse_boxes", "predict", "detect_image", "draft_elements", "facade_px",
                     "sample_palette", "main"):
            self.assertTrue(callable(getattr(FD, name)), name)


if __name__ == "__main__":
    unittest.main()
