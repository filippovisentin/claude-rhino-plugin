"""Facade benchmark on the CMP Facade Database (CC BY-SA, Tylecek & Sara, GCPR 2013).

  python tools/facade_bench.py gt ID            annotation -> ground-truth spec (data/work/ID.gt.json)
  python tools/facade_bench.py prep ID          resized photo for reading (data/work/ID.jpg)
  python tools/facade_bench.py score ID PRED    per-class IoU against the annotation (px specs: in photo pixels)
  python tools/facade_bench.py overlay ID PRED  draws the prediction over the photo (data/work/ID.overlay.jpg)
  python tools/facade_bench.py sample N         N facade ids spread over the dataset
  python tools/facade_bench.py errors ID PRED   error analysis of a px reading: per class, objects missed and
                                                invented, and the systematic offsets of the matched boxes
  python tools/facade_bench.py crop ID x0 y0 x1 y1
                                                zoomed crop of the original photo (data/work/ID.crop.jpg) for
                                                reading thin elements; x0..y1 are pixels of data/work/ID.jpg

ID is a file stem such as cmp_b0001. Scoring works in facade fractions, so it ignores the
metric scale, which a single photo cannot fix anyway. Needs Pillow for prep and overlay.
"""
import glob
import json
import os
import re
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # tools/dev -> repo
sys.path.insert(0, os.path.join(ROOT, "rhino"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from rhinospec import spec as S  # noqa: E402
from rhinospec.plan import facade_elements  # noqa: E402
from photo_tools import COLORS, expand_px, facade_part, px_boxes  # noqa: E402,F401  (shared with the runtime tools)

DATA = os.path.join(ROOT, "data", "cmp")
WORK = os.path.join(ROOT, "data", "work")
GRID = 200
CLASSES = S.FACADE_CLASSES
ID_RE = re.compile(r"^cmp_[bx]\d{4}\Z")   # ids become file paths: nothing else gets through


def _paths(fid):
    if not ID_RE.match(fid):
        raise SystemExit("bad id %r (expected like cmp_b0001)" % fid)
    return os.path.join(DATA, "base" if fid[4] == "b" else "extended", fid)


def parse_annotation(text):
    """Returns (facade_rect, [(class, x0, y0, x1, y1)]) in normalised image coordinates, y down.

    Careful: in the CMP files <x> is the row (vertical, divided by the image height) and <y> the
    column (horizontal, divided by the width). Checked against pixel multiples, e.g. 0.18164 * 1024.
    """
    objs = []
    for m in re.finditer(r"<object>(.*?)</object>", text, re.S):
        body = m.group(1)
        ys = [float(v) for v in re.findall(r"<x>\s*([-\d.eE]+)\s*</x>", body)]
        xs = [float(v) for v in re.findall(r"<y>\s*([-\d.eE]+)\s*</y>", body)]
        name = re.search(r"<labelname>\s*(\w+)\s*</labelname>", body)
        if name and len(xs) == 2 and len(ys) == 2:
            objs.append((name.group(1), min(xs), min(ys), max(xs), max(ys)))
    fac = [o for o in objs if o[0] == "facade"]
    rect = (0.0, 0.0, 1.0, 1.0)
    if fac:
        rect = (min(o[1] for o in fac), min(o[2] for o in fac), max(o[3] for o in fac), max(o[4] for o in fac))
    return rect, [o for o in objs if o[0] in CLASSES]


def read_annotation(fid):
    with open(_paths(fid) + ".xml", encoding="utf-8") as fh:
        return parse_annotation(fh.read())


def image_size(fid):
    from PIL import Image
    with Image.open(_paths(fid) + ".jpg") as im:
        return im.size


def annotation_to_spec(rect, objs, img_w, img_h, name):
    """Annotation -> facade spec in fractions. Height guessed from the median window (1.5 m tall)."""
    fx0, fy0, fx1, fy1 = rect
    fw, fh = fx1 - fx0, fy1 - fy0
    wins = [(o[4] - o[2]) / fh for o in objs if o[0] == "window"]
    H = min(80.0, max(3.0, 1.5 / statistics.median(wins))) if wins else 12.0
    W = H * (fw * img_w) / (fh * img_h)
    els = []
    for k, x0, y0, x1, y1 in objs:
        u0, u1 = (x0 - fx0) / fw, (x1 - fx0) / fw
        v0, v1 = (fy1 - y1) / fh, (fy1 - y0) / fh
        if u1 > u0 and v1 > v0:
            els.append({"k": k, "box": [round(u0, 4), round(v0, 4), round(u1 - u0, 4), round(v1 - v0, 4)]})
    return {"units": "m", "layer": "GT " + name, "clear": True, "parts": [
        {"type": "facade", "name": name, "w": round(W, 2), "h": round(H, 2), "frac": True, "els": els}]}


def ground_truth(fid):
    rect, objs = read_annotation(fid)
    iw, ih = image_size(fid)
    return annotation_to_spec(rect, objs, iw, ih, fid)



def masks(f):
    """Rasterises a validated facade into per-class sets of grid cells (fractions of w and h)."""
    out = dict((k, set()) for k in CLASSES)
    for k, (u, v, w, h), _ in facade_elements(f):
        i0, i1 = int(u / f["w"] * GRID), int((u + w) / f["w"] * GRID + 0.5)
        j0, j1 = int(v / f["h"] * GRID), int((v + h) / f["h"] * GRID + 0.5)
        for i in range(max(i0, 0), min(max(i1, i0 + 1), GRID)):
            for j in range(max(j0, 0), min(max(j1, j0 + 1), GRID)):
                out[k].add((i, j))
    return out


def _iou(a, b):
    return round(len(a & b) / float(len(a | b)), 3) if a | b else None


def image_masks(objs, boxes_px, img_w, img_h):
    """Per-class cell sets in normalised image space: (annotation objects, predicted px boxes)."""
    def fill(dst, k, x0, y0, x1, y1):
        for i in range(max(int(x0 * GRID), 0), min(max(int(x1 * GRID + 0.5), int(x0 * GRID) + 1), GRID)):
            for j in range(max(int(y0 * GRID), 0), min(max(int(y1 * GRID + 0.5), int(y0 * GRID) + 1), GRID)):
                dst[k].add((i, j))
    g = dict((k, set()) for k in CLASSES)
    p = dict((k, set()) for k in CLASSES)
    for k, x0, y0, x1, y1 in objs:
        fill(g, k, x0, y0, x1, y1)
    for k, (x0, y0, x1, y1) in boxes_px:
        fill(p, k, x0 / img_w, y0 / img_h, x1 / img_w, y1 / img_h)
    return g, p



def score_px(fid, pred_spec):
    """Scores a px prediction against the annotation in the pixels of the photo it was read from."""
    from PIL import Image
    with Image.open(os.path.join(WORK, fid + ".jpg")) as im:
        w, h = im.size
    _, objs = read_annotation(fid)
    g, p = image_masks(objs, px_boxes(pred_spec), w, h)
    return _summary(g, p)


def score(gt_spec, pred_spec):
    g, p = masks(facade_part(gt_spec)), masks(facade_part(pred_spec))
    return _summary(g, p)


def _summary(g, p):
    per = dict((k, _iou(g[k], p[k])) for k in CLASSES if g[k] or p[k])
    present = [k for k in CLASSES if g[k]]
    op = lambda m: m["window"] | m["door"] | m["shop"]
    return {
        "mIoU": round(sum(per[k] for k in present) / len(present), 3) if present else None,
        "openings_IoU": _iou(op(g), op(p)),
        "per_class": per,
        "missed": [k for k in present if not p[k]],
        "extra": [k for k in CLASSES if p[k] and not g[k]],
    }


def prep(fid, size=768):
    from PIL import Image
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, fid + ".jpg")
    with Image.open(_paths(fid) + ".jpg") as im:
        im = im.convert("RGB")
        im.thumbnail((size, size))
        im.save(out, quality=85)
        return out, im.size



def overlay(fid, pred_spec):
    from PIL import Image, ImageDraw
    (fx0, fy0, fx1, fy1), _ = read_annotation(fid)
    f = facade_part(pred_spec)
    src, _ = prep(fid)
    im = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(im)
    iw, ih = im.size
    if any(q.get("type") == "facade" and "px" in q for q in pred_spec.get("parts", [])):
        # px specs are read in the prepped photo's pixels: draw those boxes as they are.
        for k, b in px_boxes(pred_spec):
            draw.rectangle(b, outline=COLORS[k], width=2)
        out = os.path.join(WORK, fid + ".overlay.jpg")
        im.save(out, quality=85)
        return out
    for k, (u, v, w, h), _ in facade_elements(f):
        x0 = (fx0 + u / f["w"] * (fx1 - fx0)) * iw
        x1 = (fx0 + (u + w) / f["w"] * (fx1 - fx0)) * iw
        y0 = (fy1 - (v + h) / f["h"] * (fy1 - fy0)) * ih
        y1 = (fy1 - v / f["h"] * (fy1 - fy0)) * ih
        draw.rectangle([x0, y0, x1, y1], outline=COLORS[k], width=2)
    out = os.path.join(WORK, fid + ".overlay.jpg")
    im.save(out, quality=85)
    return out


def _box_iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def errors(fid, pred_spec, match=0.3):
    """Object-level error analysis of a px reading against the annotation, in pixels of ID.jpg.

    Every annotated object is matched to the predicted box of the same class it overlaps most
    (IoU >= match, each prediction used once). Reports per class: annotated, predicted, matched,
    missed (annotated, no match; with their boxes), invented (predicted, no match), the mean IoU of
    the matches and the median offsets of predicted against annotated edges, as fractions of the
    annotated width and height (left, top, right, bottom; positive = predicted edge further
    right / lower). Wrong-class confusions are listed when a missed object overlaps a predicted
    box of another class."""
    from PIL import Image
    with Image.open(os.path.join(WORK, fid + ".jpg")) as im:
        W, H = im.size
    _, objs = read_annotation(fid)
    gt = [(k, [x0 * W, y0 * H, x1 * W, y1 * H]) for k, x0, y0, x1, y1 in objs]
    pred = [(k, [float(v) for v in b]) for k, b in px_boxes(pred_spec)]
    used = set()
    report = {}
    for cls in CLASSES:
        g = [b for k, b in gt if k == cls]
        p = [(i, b) for i, (k, b) in enumerate(pred) if k == cls]
        if not g and not p:
            continue
        ious, offs, missed = [], [], []
        for b in sorted(g, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
            best = max(((_box_iou(b, q), i, q) for i, q in p if i not in used), default=(0, None, None))
            if best[0] >= match:
                used.add(best[1])
                ious.append(best[0])
                q = best[2]
                gw, gh = b[2] - b[0], b[3] - b[1]
                offs.append(((q[0] - b[0]) / gw, (q[1] - b[1]) / gh, (q[2] - b[2]) / gw, (q[3] - b[3]) / gh))
            else:
                conf = [pred[i][0] for i in range(len(pred)) if pred[i][0] != cls and _box_iou(b, pred[i][1]) >= match]
                missed.append([round(v) for v in b] + ([conf[0]] if conf else []))
        invented = [[round(v) for v in q] for i, q in p if i not in used]
        med = lambda xs: round(statistics.median(xs), 2) if xs else None
        report[cls] = {"gt": len(g), "pred": len(p), "matched": len(ious),
                       "iou": round(sum(ious) / len(ious), 2) if ious else None,
                       "offset_ltrb": [med([o[j] for o in offs]) for j in range(4)] if offs else None,
                       "missed": missed[:8], "invented": invented[:8]}
    return report


def crop(fid, box, size=768):
    """Crops the original photo around box (pixels of the prepped ID.jpg) and enlarges it to size.
    Returns (path, scale): a pixel (xc, yc) of the crop is (x0 + xc / scale, y0 + yc / scale)
    in ID.jpg, the frame every px box is read in."""
    from PIL import Image
    with Image.open(os.path.join(WORK, fid + ".jpg")) as small:
        sw, sh = small.size
    x0, y0, x1, y1 = [float(v) for v in box]
    if not (0 <= x0 < x1 <= sw and 0 <= y0 < y1 <= sh):
        raise SystemExit("crop box must lie inside the %dx%d photo" % (sw, sh))
    with Image.open(_paths(fid) + ".jpg") as im:
        k = im.size[0] / float(sw)            # original pixels per prepped pixel
        part = im.convert("RGB").crop((int(x0 * k), int(y0 * k), int(x1 * k), int(y1 * k)))
        scale = min(size / (x1 - x0), size / (y1 - y0))
        part = part.resize((max(1, int((x1 - x0) * scale)), max(1, int((y1 - y0) * scale))), Image.LANCZOS)
        out = os.path.join(WORK, fid + ".crop.jpg")
        part.save(out, quality=88)
    return out, scale


def all_ids():
    return sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(DATA, "*", "cmp_*.xml")))


def sample(n):
    ids = all_ids()
    step = max(1, len(ids) // n)
    return ids[::step][:n]


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    cmd, arg = argv[1], argv[2]
    if cmd == "gt":
        os.makedirs(WORK, exist_ok=True)
        out = os.path.join(WORK, arg + ".gt.json")
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(ground_truth(arg), fh, separators=(",", ":"))
        print(out)
    elif cmd == "prep":
        path, size = prep(arg)
        print("%s %dx%d" % (path, size[0], size[1]))
    elif cmd == "score" and len(argv) > 3:
        pred = _load(argv[3])
        has_px = any(q.get("type") == "facade" and "px" in q for q in pred.get("parts", []))
        print(json.dumps(score_px(arg, pred) if has_px else score(ground_truth(arg), pred)))
    elif cmd == "overlay" and len(argv) > 3:
        print(overlay(arg, _load(argv[3])))
    elif cmd == "errors" and len(argv) > 3:
        for k, v in errors(arg, _load(argv[3])).items():
            print(k, json.dumps(v))
    elif cmd == "crop" and len(argv) > 6:
        if not ID_RE.match(arg):
            raise SystemExit("bad id")
        path, scale = crop(arg, argv[3:7])
        x0, y0 = float(argv[3]), float(argv[4])
        print("%s  ID.jpg x = %g + xc / %.4g, y = %g + yc / %.4g" % (path, x0, scale, y0, scale))
    elif cmd == "sample":
        print(" ".join(sample(int(arg))))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
