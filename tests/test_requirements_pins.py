"""requirements-detector*.txt pin the versions of the reference venv (data/venv-det). The
version a module reports (cv2.__version__ "5.0.0") can differ from its pip distribution's
("opencv-python 5.0.0.93"), so the pins are checked against the installed distributions."""
import os
import re
import subprocess
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV = os.path.join(ROOT, "data", "venv-det", "Scripts" if os.name == "nt" else "bin",
                    "python.exe" if os.name == "nt" else "python")


def pins(name):
    out = {}
    with open(os.path.join(ROOT, name), encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"^([A-Za-z0-9_.\-]+)==(\S+)", line.strip())
            if m:
                out[m.group(1).lower()] = m.group(2)
    return out


class Pins(unittest.TestCase):
    def test_every_package_is_pinned(self):
        for name in ("requirements-detector.txt", "requirements-detector-cpu.txt"):
            self.assertEqual(set(pins(name)), {"torch", "torchvision", "ultralytics", "numpy", "opencv-python",
                                               "pillow", "psutil"}, name)

    def test_cpu_file_differs_only_in_the_torch_build(self):
        gpu, cpu = pins("requirements-detector.txt"), pins("requirements-detector-cpu.txt")
        for k in gpu:
            self.assertEqual(gpu[k].replace("+cu128", "+cpu"), cpu[k], k)

    @unittest.skipUnless(os.path.exists(VENV), "needs the reference venv data/venv-det")
    def test_gpu_pins_match_the_reference_venv(self):
        want = pins("requirements-detector.txt")
        code = "import json,importlib.metadata as m;print(json.dumps({p: m.version(p) for p in %r}))" % sorted(want)
        got = subprocess.run([VENV, "-I", "-c", code], capture_output=True, text=True, timeout=120)
        self.assertEqual(got.returncode, 0, got.stderr[-400:])
        import json
        self.assertEqual({k.lower(): v for k, v in json.loads(got.stdout).items()}, want)


if __name__ == "__main__":
    unittest.main()
