"""silhouette.py finds the scene model installed by the setup (RHINO_SCENE_WEIGHTS, set by run-tool)
and otherwise the repo's data/det-runs, as before."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
try:
    import numpy  # noqa: F401
    import silhouette as S
except ImportError:  # pragma: no cover
    S = None


@unittest.skipIf(S is None, "needs numpy")
class SceneWeights(unittest.TestCase):
    def test_installed_model_wins(self):
        with tempfile.TemporaryDirectory() as d:
            w = os.path.join(d, "scene2.pt")
            open(w, "w").close()
            self.assertEqual(S.scene_weights({"RHINO_SCENE_WEIGHTS": w}), w)

    def test_missing_file_falls_back_to_the_repo(self):
        self.assertEqual(S.scene_weights({"RHINO_SCENE_WEIGHTS": os.path.join(ROOT, "nope.pt")}), S.scene_weights({}))
        self.assertIn(os.path.join("data", "det-runs"), S.scene_weights({}))


if __name__ == "__main__":
    unittest.main()


@unittest.skipIf(S is None, "needs numpy")
class IsolatedImports(unittest.TestCase):
    def test_silhouette_finds_photo3d_under_python_I(self):
        """run-tool starts Python with -I, which leaves tools/ off sys.path: silhouette.py must add it
        itself, or compare --calib fails on `import photo3d`."""
        import subprocess
        path = os.path.join(ROOT, "tools", "silhouette.py")
        code = ("import importlib.util as u; s = u.spec_from_file_location('silhouette', %r); "
                "m = u.module_from_spec(s); s.loader.exec_module(m); import photo3d; print('ok')" % path)
        p = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60,
                           cwd=tempfile.gettempdir())
        self.assertEqual(p.stdout.strip(), "ok", p.stderr[-300:])
