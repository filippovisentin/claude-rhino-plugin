"""Report for trained facade detectors: same test photos for every model.

    python tools/dev/facade_report.py OUT.md RUN [RUN ...]     # RUN = folder under data/det-runs

For each run:
  - CMP test (22 photos Claude read blind): mIoU per photo and per class, detector vs Claude
    (facade_bench pixel IoU), plus YOLO mAP50 on all CMP classes;
  - hznu held-out (66 modern Hangzhou facades) and CFP test (60 street views): mAP50 for
    window and door only, the classes those datasets annotate.
"""
import contextlib
import io
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_HERE, os.path.dirname(_HERE)]  # tools/dev, then the runtime tools
import facade_yolo as Y  # noqa: E402

RUNS = os.path.join(Y.FB.ROOT, "data", "det-runs")
ALL = Y.OUT + "-all"


def _val(model, yaml, classes=None):
    m = model.val(data=os.path.join(ALL, yaml), split="test", imgsz=1024, batch=8, classes=classes,
                  plots=False, verbose=False, project=os.path.join(RUNS, "_val"), name="v", exist_ok=True)
    per = dict((Y.NAMES[int(c)], round(float(a), 3)) for c, a in zip(m.ap_class_index, m.box.ap50))
    return round(float(m.box.map50), 3), per


def run_report(name):
    from ultralytics import YOLO
    weights = os.path.join(RUNS, name, "weights", "best.pt")
    model = YOLO(weights)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        Y.compare(weights)
    out = ["## %s" % name, "", "### CMP test vs Claude (pixel IoU, 22 photos)", "", "```", buf.getvalue().rstrip(), "```", ""]
    rows = [("CMP test, all classes", "test_cmp.yaml", None),
            ("hznu held-out, window+door", "test_hznu.yaml", [0, 1]),
            ("CFP test, window+door", "test_cfp.yaml", [0, 1])]
    out += ["### YOLO mAP50 per test set", "", "| set | mAP50 | window | door |", "|---|---|---|---|"]
    for label, yaml, cls in rows:
        if not os.path.exists(os.path.join(ALL, yaml)):
            continue
        m, per = _val(model, yaml, cls)
        out.append("| %s | %s | %s | %s |" % (label, m, per.get("window", "-"), per.get("door", "-")))
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    parts = ["# Facade detector report", "", time.strftime("%Y-%m-%d %H:%M"), ""]
    for name in argv[1:]:
        if os.path.exists(os.path.join(RUNS, name, "weights", "best.pt")):
            parts.append(run_report(name))
        else:
            parts.append("## %s\n\nno weights\n" % name)
    with open(argv[0], "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
