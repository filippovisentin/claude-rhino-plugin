"""tools/ holds only what the plugin runs on any PC; training, benchmarks and experiments live in
tools/dev/ and still find the repo's data/, rhino/ and the runtime tools from any folder."""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
DEV = os.path.join(TOOLS, "dev")
RUNTIME = {"rectify.py", "photo3d.py", "silhouette.py", "export_mesh.py", "facade_regular.py", "facade_detect.py"}
OPTIONAL = {"photo_tools.py"}
MOVED = ["facade_bench.py", "facade_yolo.py", "train_data.py", "train_report.py", "ensemble_report.py",
         "facade_report.py", "photo_bench.py", "clean_pick.py", "facade_refine.py", "fuzz_specs.py",
         "glass_read.py", "solid_audit.py", "auto_rectify.py", "scenarios"]


class Layout(unittest.TestCase):
    def test_runtime_only_in_tools(self):
        here = {f for f in os.listdir(TOOLS) if f not in ("dev", "__pycache__")}
        self.assertTrue(RUNTIME <= here, RUNTIME - here)
        self.assertEqual(here - RUNTIME - OPTIONAL, set())

    def test_dev_tools_moved(self):
        for f in MOVED:
            self.assertTrue(os.path.exists(os.path.join(DEV, f)), f)

    def test_dev_tools_find_the_repo(self):
        sys.path[:0] = [DEV, TOOLS]
        import facade_bench
        self.assertEqual(os.path.normcase(os.path.abspath(facade_bench.ROOT)), os.path.normcase(ROOT))

    def test_runs_from_another_folder(self):
        with tempfile.TemporaryDirectory() as cwd:
            p = subprocess.run([sys.executable, "-I", os.path.join(DEV, "train_data.py"), "sources"],
                               cwd=cwd, capture_output=True, text=True, timeout=120)
        self.assertEqual(p.returncode, 0, p.stderr[-400:])

    def test_auto_rectify_records_its_result(self):
        with open(os.path.join(DEV, "auto_rectify.py"), encoding="utf-8") as fh:
            head = fh.read(1500)
        self.assertIn("3.47", head)
        self.assertIn("1.55", head)


if __name__ == "__main__":
    unittest.main()


class Docs(unittest.TestCase):
    def test_no_doc_points_at_a_moved_tool_old_path(self):
        """Copy-paste commands in the docs must name tools/dev/ for the moved scripts."""
        import glob
        import re
        names = "|".join(re.escape(f[:-3]) if f.endswith(".py") else re.escape(f) for f in MOVED)
        old = re.compile(r"tools[/\\]+(?:%s)\b" % names)
        files = [os.path.join(ROOT, f) for f in ("README.md", "MODELS-LICENSE.md")]
        files += glob.glob(os.path.join(ROOT, "docs", "*.md")) + glob.glob(os.path.join(ROOT, "skills", "*", "*.md"))
        files += glob.glob(os.path.join(ROOT, "tests", "fixtures", "**", "*.md"), recursive=True)
        files += glob.glob(os.path.join(DEV, "**", "*.py"), recursive=True)
        bad = []
        for f in files:
            with open(f, encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if old.search(line):
                        bad.append("%s:%d: %s" % (os.path.relpath(f, ROOT), i, line.strip()[:100]))
        self.assertEqual(bad, [])
