"""Single models against their fusion (facade_yolo.fuse_boxes), on the report's fair photos.

    data\\venv-det\\Scripts\\python.exe tools/dev/ensemble_report.py OUT.md [RUN ...] [--fuse A+B[:wa,wb] ...]

Uses the groups train_report.py built in data/det-runs/_eval (photos no model has seen, human
labels only) and scores every entry the same way: box mAP50 (101-point, matches at IoU 0.5) per
group on the classes that group labels, and pixel IoU against Claude's readings on cmp22.
Defaults: parts2m, parts11s, and their fusion (mode max) with equal weights and with the default
weights (first model 2, others 1), the fusion detect_facade uses.
"""
import contextlib
import io
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_HERE, os.path.dirname(_HERE)]  # tools/dev, then the runtime tools
import facade_yolo as FY  # noqa: E402
import train_data as TD  # noqa: E402
import train_report as TR  # noqa: E402


def ap50(preds, gts):
    """preds [(conf, img, box)], gts {img: [box]} for one class -> AP at IoU 0.5 (101-point)."""
    n = sum(len(v) for v in gts.values())
    if not n:
        return None
    used = dict((k, [False] * len(v)) for k, v in gts.items())
    tp = []
    for c, img, b in sorted(preds, key=lambda p: -p[0]):
        best, bi = 0.5, -1
        for i, g in enumerate(gts.get(img, [])):
            v = FY._iou(b, g)
            if v >= best and not used[img][i]:
                best, bi = v, i
        if bi >= 0:
            used[img][bi] = True
        tp.append(bi >= 0)
    rec, prec, t = [], [], 0
    for i, hit in enumerate(tp):
        t += hit
        rec.append(t / n)
        prec.append(t / (i + 1))
    env = prec[:] + [0.0]
    for i in range(len(env) - 2, -1, -1):
        env[i] = max(env[i], env[i + 1])
    total = 0.0
    for r in (i / 100.0 for i in range(101)):
        total += next((env[i] for i, x in enumerate(rec) if x >= r), 0.0)
    return total / 101.0


def labels(group):
    """{img path: [(class, box px)]} from the group's YOLO labels."""
    from PIL import Image
    d = os.path.join(TR.EVAL, group)
    out = {}
    for f in sorted(os.listdir(os.path.join(d, "images", "test"))):
        img = os.path.join(d, "images", "test", f)
        with Image.open(img) as im:
            w, h = im.size
        objs = []
        lab = os.path.join(d, "labels", "test", f.rsplit(".", 1)[0] + ".txt")
        if os.path.exists(lab):
            for ln in open(lab).read().split("\n"):
                if ln.strip():
                    c, x, y, bw, bh = ln.split()
                    x, y, bw, bh = float(x) * w, float(y) * h, float(bw) * w, float(bh) * h
                    objs.append((TD.PARTS[int(c)], [x - bw / 2, y - bh / 2, x + bw / 2, y + bh / 2]))
        out[img] = objs
    return out


def score_group(weights, group, model_weights=None):
    gt = labels(group)
    classes = [k for k in TD.PARTS if k in TR.GROUPS[group]]
    preds = dict((k, []) for k in classes)
    for img in gt:
        dets, _ = FY.predict(weights, img, 0.001, model_weights)
        for k, c, *b in dets:
            if k in preds:
                preds[k].append((c, img, b))
    per = {}
    for k in classes:
        g = dict((img, [b for kk, b in objs if kk == k]) for img, objs in gt.items())
        a = ap50(preds[k], g)
        if a is not None:
            per[k] = round(a, 3)
    return (round(sum(per.values()) / len(per), 3) if per else None), per


def vs_claude(weights):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        FY.compare(weights)
    lines = buf.getvalue().splitlines()
    mean = next(ln for ln in lines if ln.startswith("MEAN")).split()
    per = dict((ln.split()[0], ln.split()[1]) for ln in lines[lines.index("per class   det  claude") + 1:] if ln.strip())
    return mean[1], mean[3], per


def entries(argv):
    runs, fuse, out = [], [], []
    it = iter(argv)
    for a in it:
        if a == "--fuse":
            fuse.append(next(it))
        else:
            runs.append(a)
    if not runs and not fuse:
        runs, fuse = ["parts2m", "parts11s"], ["parts2m+parts11s:1,1", "parts2m+parts11s"]
    w = lambda r: os.path.join(TD.RUNS, r, "weights", "best.pt")
    for r in runs:
        out.append((r, [w(r)], None))
    for f in fuse:
        names, _, mw = f.partition(":")
        out.append(("fuse " + f, [w(r) for r in names.split("+")], [float(x) for x in mw.split(",")] if mw else None))
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    todo = entries(argv[2:])
    groups = [g for g in ("cmp22", "modern", "oxford", "monumai") if os.path.isdir(os.path.join(TR.EVAL, g))]
    lines = ["# Single models and fusions", "", time.strftime("%Y-%m-%d %H:%M"), "",
             "Same photos as report4 (no model has seen them, human labels only); every row scored by "
             "tools/dev/ensemble_report.py, so rows compare with each other, not digit for digit with Ultralytics' val.", ""]
    summary = ["| entry | " + " | ".join(groups) + " | IoU vs Claude (cmp22) | openings IoU |",
               "|---|" + "---|" * (len(groups) + 2)]
    detail = []
    for name, ws, mw in todo:
        if not all(os.path.exists(p) for p in ws):
            continue
        cells = []
        for g in groups:
            m, per = score_group(ws, g, mw)
            cells.append("-" if m is None else "%.3f" % m)
            detail.append((g, name, per))
        miou, open_iou, per_cls = (vs_claude(ws) if mw is None else vs_claude_weighted(ws, mw))
        summary.append("| %s | %s | %s | %s |" % (name, " | ".join(cells), miou, open_iou))
        detail.append(("claude", name, per_cls))
        print(summary[-1], flush=True)
    lines += summary + [""]
    for g in groups + ["claude"]:
        rows = [(n, p) for gg, n, p in detail if gg == g]
        classes = sorted(set(k for _, p in rows for k in p), key=lambda k: TD.PARTS.index(k) if k in TD.PARTS else 99)
        title = "pixel IoU per class on cmp22" if g == "claude" else "%s mAP50 per class" % g
        lines += ["## " + title, "", "| entry | " + " | ".join(classes) + " |", "|---|" + "---|" * len(classes)]
        lines += ["| %s | %s |" % (n, " | ".join(str(p.get(k, "-")) for k in classes)) for n, p in rows] + [""]
    with open(argv[1], "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(argv[1])
    return 0


def vs_claude_weighted(ws, mw):
    """compare() with model weights: predict() takes them from here."""
    orig = FY.predict
    FY.predict = lambda w, p, conf=0.25, m=None: orig(w, p, conf, mw)
    try:
        return vs_claude(ws)
    finally:
        FY.predict = orig


if __name__ == "__main__":
    sys.exit(main(sys.argv))
