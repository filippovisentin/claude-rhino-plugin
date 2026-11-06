"""The detector picks its device itself: GPU 0 when torch sees one, else the CPU. Without this,
Ultralytics reuses the device stored in the weights (GPU 0 from training) and fails on a PC
without a GPU."""
import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import facade_detect as FY  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "detector", "c_0075.jpg")
VENV = os.path.join(ROOT, "data", "venv-det", "Scripts" if os.name == "nt" else "bin",
                    "python.exe" if os.name == "nt" else "python")
RUNS = [os.path.join(ROOT, "data", "det-runs", r, "weights", "best.pt") for r in ("parts2m", "parts11s")]


class PickDevice(unittest.TestCase):
    def test_gpu_when_cuda(self):
        self.assertEqual(FY.pick_device({}, cuda=True), 0)

    def test_cpu_without_cuda(self):
        self.assertEqual(FY.pick_device({}, cuda=False), "cpu")

    def test_env_forces_cpu(self):
        self.assertEqual(FY.pick_device({"RHINO_FACADE_DEVICE": "cpu"}, cuda=True), "cpu")

    def test_env_cuda_without_gpu_falls_back(self):
        self.assertEqual(FY.pick_device({"RHINO_FACADE_DEVICE": "cuda"}, cuda=False), "cpu")

    def test_bad_env_ignored(self):
        self.assertEqual(FY.pick_device({"RHINO_FACADE_DEVICE": "x"}, cuda=True), 0)


@unittest.skipUnless(os.path.exists(FIXTURE) and os.path.exists(VENV) and all(map(os.path.exists, RUNS)),
                     "needs the detector fixture, data/venv-det and trained weights")
class RunsWithoutGpu(unittest.TestCase):
    def test_hidden_gpu_runs_on_cpu(self):
        env = dict(os.environ, CUDA_VISIBLE_DEVICES="", YOLO_OFFLINE="1")
        p = subprocess.run([VENV, "-I", os.path.join(ROOT, "tools", "facade_detect.py"), "detect-image",
                            FIXTURE, os.pathsep.join(RUNS), "0.25"],
                           capture_output=True, text=True, env=env, timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        out = json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(out["device"], "cpu")


if __name__ == "__main__":
    unittest.main()
