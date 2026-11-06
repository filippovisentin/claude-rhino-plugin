"""Report for the parts and scene models (tools/train_data.py), against yesterday's detectors.

    data\\venv-det\\Scripts\\python.exe tools/train_report.py OUT.md [NEW_PARTS_RUN] [OLD_RUN ...]

Fair by construction:
  - only photos no compared model has trained or validated on (today's test split minus anything
    in yesterday's train/val), so yesterday's hznu and CFP test sets, which partly went into
    today's training, are not used;
  - only each dataset's own human labels, never the teachers' boxes that fill today's labels
    (they are yesterday's model outputs and would favour it).

Groups (each scored only on the classes its source labels):
  cmp22     the 22 CMP photos Claude read blind: all 10 CMP classes, plus pixel IoU against Claude
  modern    hznu and CFP photos: window, door
  oxford    Oxford street views: window, door, balcony, shop (no old model has seen Oxford)
  monumai   monuments: arch, pediment, pediment_seg, oculus, finial, pillar (new classes)
  scene     the scene model on its own test split, per class, boxes and masks
"""
import contextlib
import io
import os
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [_HERE, os.path.dirname(_HERE)]  # tools/dev, then the runtime tools
import facade_bench as FB  # noqa: E402
import facade_yolo as FY  # noqa: E402
import train_data as TD  # noqa: E402

EVAL = os.path.join(TD.RUNS, "_eval")
GROUPS = {"cmp22": set(FY.NAMES), "modern": {"window", "door"},
          "oxford": {"window", "door", "balcony", "shop"},
          "monumai": {"arch", "pediment", "pediment_seg", "oculus", "finial", "pillar"}}


def _stems(d):
    return set(f.rsplit(".", 1)[0] for f in os.listdir(d)) if os.path.isdir(d) else set()


def fair_test():
    """Test photos of the current parts set that no model has seen in training or validation:
    yesterday's datasets, and every run's seen.txt (written by train_data.py train)."""
    seen = set()
    for root in (os.path.join(TD.DATA, "yolo-all"), os.path.join(TD.DATA, "yolo-modern"), os.path.join(TD.DATA, "yolo")):
        for s in ("train", "val"):
            seen |= _stems(os.path.join(root, "images", s))
    for run in os.listdir(TD.RUNS):
        f = os.path.join(TD.RUNS, run, "seen.txt")
        if os.path.exists(f):
            with open(f) as fh:
                seen |= set(l.strip() for l in fh if l.strip())
    return _stems(os.path.join(TD.DATA, "yolo-parts", "images", "test")) - seen


def human_objects():
    """{id: (image path, group, [(class, x0, y0, x1, y1)])} from the sources' own annotations."""
    out = {}
    blind = set(FY.test_ids())
    for fid in FB.all_ids():
        if fid in blind:
            out[fid] = (FB._paths(fid) + ".jpg", "cmp22", FB.read_annotation(fid)[1])
    for fid in FY.hznu_ids():
        out[fid] = (os.path.join(FY.HZNU, fid + ".jpg"), "modern", FY.hznu_objs(fid))
    for fid, base in FY.cfp_entries().items():
        out[fid] = (FY._image(base), "modern", FY.labelme_objs(base + ".json", FY._image(base)))
    if TD.have("oxford"):
        for fid, img, objs in TD._oxford_items(0):
            out[fid] = (img, "oxford", objs)
    if TD.have("monumai"):
        for fid, img, objs in TD._monumai_items(0):
            out[fid] = (img, "monumai", objs)
    return out


def build_groups():
    ids = fair_test()
    objs = human_objects()
    sets = {}
    for fid in sorted(ids):
        if fid not in objs:
            continue
        img, group, ob = objs[fid]
        sets.setdefault(group, []).append((fid, img, [o for o in ob if o[0] in GROUPS[group]]))
    if os.path.isdir(EVAL):
        shutil.rmtree(EVAL)
    for group, items in sets.items():
        out = os.path.join(EVAL, group)
        for d in ("images/test", "labels/test", "images/train"):
            os.makedirs(os.path.join(out, d))
        for fid, img, ob in items:
            dst = os.path.join(out, "images", "test", fid + ".jpg")
            FY._copy_small(img, dst)
            lines = [ln for ln in (TD.box_line(TD.PARTS.index(k), *b) for k, *b in ob) if ln]
            with open(os.path.join(out, "labels", "test", fid + ".txt"), "w") as fh:
                fh.write("\n".join(lines) + ("\n" if lines else ""))
        with open(os.path.join(out, "eval.yaml"), "w") as fh:
            fh.write("path: %s\ntrain: images/test\nval: images/test\ntest: images/test\nnames:\n" % out.replace("\\", "/"))
            for i, n in enumerate(TD.PARTS):
                fh.write("  %d: %s\n" % (i, n))
    return dict((g, len(v)) for g, v in sets.items())


def score(weights, group):
    """mAP50 over the group's classes the model knows, and per class."""
    YOLO = TD._models()
    model = YOLO(weights)
    known = [i for i, n in enumerate(TD.PARTS) if n in GROUPS[group] and i < len(model.names)
             and model.names[i] == n]
    if not known:
        return None, {}
    m = model.val(data=os.path.join(EVAL, group, "eval.yaml"), split="test", imgsz=1024, batch=8, classes=known,
                  plots=False, verbose=False, project=os.path.join(TD.RUNS, "_val"), name="v", exist_ok=True)
    per = dict((TD.PARTS[int(c)], round(float(a), 3)) for c, a in zip(m.ap_class_index, m.box.ap50) if int(c) in known)
    return (round(sum(per.values()) / len(per), 3) if per else None), per


def claude_compare(weights):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        FY.compare(weights)
    return buf.getvalue().rstrip()


def scene_report(weights):
    YOLO = TD._models()
    m = YOLO(weights).val(data=os.path.join(TD.DATA, "yolo-scene", "scene.yaml"), split="test", imgsz=1024, batch=8,
                          plots=False, verbose=False, project=os.path.join(TD.RUNS, "_val"), name="s", exist_ok=True)
    rows = ["| class | box mAP50 | mask mAP50 |", "|---|---|---|"]
    for c, b, s in zip(m.ap_class_index, m.box.ap50, m.seg.ap50):
        rows.append("| %s | %.3f | %.3f |" % (TD.SCENE[int(c)] if int(c) < len(TD.SCENE) else c, b, s))
    rows.append("| **all** | **%.3f** | **%.3f** |" % (m.box.map50, m.seg.map50))
    return "\n".join(rows)


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    out_md = argv[1]
    new = argv[2] if len(argv) > 2 else "parts2m"
    old = argv[3:] or ["parts11s", "all11s", "cmp11s"]
    runs = [r for r in [new] + old if os.path.exists(os.path.join(TD.RUNS, r, "weights", "best.pt"))]
    sizes = build_groups()
    lines = ["# Parts and scene models: report", "", time.strftime("%Y-%m-%d %H:%M"), "",
             "Photos no compared model has seen, human labels only. Photos per group: %s." %
             ", ".join("%s %d" % kv for kv in sorted(sizes.items())), ""]
    for group in ("cmp22", "modern", "oxford", "monumai"):
        if group not in sizes:
            continue
        classes = [n for n in TD.PARTS if n in GROUPS[group]]
        lines += ["## %s (%d photos)" % (group, sizes[group]), "",
                  "| model | mAP50 | " + " | ".join(classes) + " |", "|---|---|" + "---|" * len(classes)]
        for r in runs:
            m, per = score(os.path.join(TD.RUNS, r, "weights", "best.pt"), group)
            lines.append("| %s | %s | %s |" % (r, "-" if m is None else m, " | ".join(str(per.get(c, "-")) for c in classes)))
        lines.append("")
    for r in runs:
        lines += ["## %s vs Claude on cmp22 (pixel IoU, CMP classes)" % r, "", "```", claude_compare(
            os.path.join(TD.RUNS, r, "weights", "best.pt")), "```", ""]
    for sr in [r for r in sorted(os.listdir(TD.RUNS)) if r.startswith("scene")]:
        sw = os.path.join(TD.RUNS, sr, "weights", "best.pt")
        if os.path.exists(sw):
            lines += ["## %s on the scene test split" % sr, "", "People and poles partly come from teacher models.", "",
                      scene_report(sw), ""]
    with open(out_md, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(out_md)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
