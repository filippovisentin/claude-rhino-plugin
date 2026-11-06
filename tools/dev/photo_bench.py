"""Benchmark on ordinary perspective photos (people's street photos, not rectified elevations).

Datasets (in data/, not in git):
  labelme  LabelMeFacade, 945 LabelMe photos with colour label maps (research use only)
           Frohlich, Rodner, Denzler, ICPR 2010. github.com/cvjena/labelmefacade
  hznu     hznu_facade, 624 Hangzhou photos with window/door polygons (CC BY 4.0)
           Data in Brief 2025, doi 10.17632/k387xkyc5f.1

  python tools/photo_bench.py pick DATASET N                 N single-facade photos, best first
  python tools/photo_bench.py prep DATASET ID                resized photo to read (data/work/ID.jpg)
  python tools/photo_bench.py rect ID "x,y x,y x,y x,y" [--ratio W/H] [--face FACE]
                                                             straightened facade (data/work/ID.rect.jpg)
  python tools/photo_bench.py score DATASET ID PRED          window/door IoU in the original photo

PRED is a facade spec with px, or a block whose faces have px (each face straightened with
--face FACE is read on ID.FACE.rect.jpg). If ID.rect.json exists its boxes are read on the straightened image
and are projected back through the inverse homography before scoring, so the score covers the
whole photo -> corners -> straighten -> read chain.
"""
import glob
import json
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # tools/dev -> repo
sys.path[:0] = [HERE, os.path.dirname(HERE)]  # tools/dev, then the runtime tools
import rectify as rc  # noqa: E402

WORK = os.path.join(ROOT, "data", "work")
SIZE = 768
ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,120}\Z")
CLASSES = ("window", "door")
LABELME_COLORS = {"window": (0, 0, 128), "door": (128, 128, 0), "building": (128, 0, 0)}


def _id(fid):
    if not ID_RE.match(fid) or ".." in fid:
        raise SystemExit("bad id %r" % fid)
    return fid


# --- datasets --------------------------------------------------------------------------------

def labelme_paths(fid):
    base = os.path.join(ROOT, "data", "labelmefacade")
    return os.path.join(base, "images", _id(fid) + ".jpg"), os.path.join(base, "labels", fid + ".png")


def hznu_root():
    hits = glob.glob(os.path.join(ROOT, "data", "hznu", "**", "*.json"), recursive=True)
    return os.path.dirname(hits[0]) if hits else None


def hznu_paths(fid):
    root = hznu_root()
    if root is None:
        raise SystemExit("hznu_facade not unpacked under data/hznu")
    for ext in (".jpg", ".JPG", ".jpeg", ".png"):
        p = os.path.join(root, _id(fid) + ext)
        if os.path.exists(p):
            return p, os.path.join(root, fid + ".json")
    raise SystemExit("no image for %s" % fid)


def gt_masks(dataset, fid, size):
    """{class: bool array of shape (h, w)} at the given (w, h)."""
    w, h = size
    if dataset == "labelme":
        with Image.open(labelme_paths(fid)[1]) as lab:
            a = np.asarray(lab.convert("RGB").resize((w, h), Image.NEAREST))
        return dict((k, np.all(a == LABELME_COLORS[k], axis=-1)) for k in CLASSES)
    if dataset == "hznu":
        img_path, js = hznu_paths(fid)
        with Image.open(img_path) as im:
            W, H = im.size
        with open(js, encoding="utf-8") as fh:
            data = json.load(fh)
        out = {}
        for k in CLASSES:
            m = Image.new("1", (w, h), 0)
            d = ImageDraw.Draw(m)
            for poly in hznu_polygons(data, k):
                d.polygon([(x * w / W, y * h / H) for x, y in poly], fill=1)
            out[k] = np.asarray(m, dtype=bool)
        return out
    raise SystemExit("unknown dataset %r" % dataset)


def hznu_polygons(data, cls):
    """Polygons of one class from a hznu JSON (LabelMe-style shapes or COCO-like lists)."""
    shapes = data.get("shapes") or data.get("annotations") or data.get("objects") or []
    out = []
    for s in shapes:
        label = str(s.get("label") or s.get("category") or s.get("name") or "").lower()
        if not label.startswith(cls):
            continue
        pts = s.get("points") or s.get("polygon") or s.get("segmentation")
        if pts and isinstance(pts[0], (int, float)):
            pts = list(zip(pts[0::2], pts[1::2]))
        if pts and len(pts) >= 3:
            out.append([(float(x), float(y)) for x, y in pts])
    return out


def image_path(dataset, fid):
    return labelme_paths(fid)[0] if dataset == "labelme" else hznu_paths(fid)[0]


# --- commands --------------------------------------------------------------------------------

def prep(dataset, fid):
    os.makedirs(WORK, exist_ok=True)
    out = os.path.join(WORK, fid + ".jpg")
    with Image.open(image_path(dataset, fid)) as im:
        im = im.convert("RGB")
        im.thumbnail((SIZE, SIZE))
        im.save(out, quality=88)
        return out, im.size


def rect(fid, corners, ratio=None, face=None):
    src = os.path.join(WORK, _id(fid) + ".jpg")
    fid = fid + "." + face if face else fid
    with Image.open(src) as im:
        out, r = rc.rectify(im, corners, ratio, SIZE)
    dst = os.path.join(WORK, fid + ".rect.jpg")
    out.save(dst, quality=88)
    with open(os.path.join(WORK, fid + ".rect.json"), "w", encoding="utf-8") as fh:
        json.dump({"corners": corners, "size": list(out.size), "ratio": r}, fh)
    return dst, out.size, r


FACES = ("front", "right", "back", "left")


def _faces(pred):
    """(face name or None, facade-like part with px and els) for every read facade or block face."""
    out = []
    for q in pred["parts"]:
        if q.get("type") == "facade":
            out.append((None, q))
        elif q.get("type") == "block":
            out.extend((k, q["faces"][k]) for k in FACES if "px" in q.get("faces", {}).get(k, {}))
    return out


def _homography(fid, face):
    """rect -> photo homography for one face, or None when it was read on the photo itself.
    A block face uses <id>.<face>.rect.json, falling back to <id>.rect.json."""
    names = ([fid + "." + face] if face else []) + [fid]
    for name in names:
        side = os.path.join(WORK, name + ".rect.json")
        if os.path.exists(side):
            with open(side, encoding="utf-8") as fh:
                meta = json.load(fh)
            w, h = meta["size"]
            return rc.homography([(0, 0), (w, 0), (w, h), (0, h)], [tuple(p) for p in meta["corners"]])
    return None


def pred_quads(pred, fid):
    """Predicted boxes as quads in the prepped photo's pixels: [(k, [(x, y) * 4])]."""
    from facade_bench import expand_px
    out = []
    for face, f in _faces(pred):
        H = _homography(fid, face)
        def back(x, y, H=H):
            if H is None:
                return (x, y)
            p = H @ np.array([x, y, 1.0])
            return (p[0] / p[2], p[1] / p[2])
        for el in f["els"]:
            for a, b, c, d in expand_px(el):
                out.append((el["k"], [back(a, b), back(c, b), back(c, d), back(a, d)]))
    return out


def score(dataset, fid, pred):
    with Image.open(os.path.join(WORK, _id(fid) + ".jpg")) as im:
        size = im.size
    gt = gt_masks(dataset, fid, size)
    masks = {}
    for k in CLASSES:
        m = Image.new("1", size, 0)
        d = ImageDraw.Draw(m)
        for kk, quad in pred_quads(pred, fid):
            if kk == k or (k == "window" and kk == "shop"):
                d.polygon(quad, fill=1)
        masks[k] = np.asarray(m, dtype=bool)
    out = {}
    for k in CLASSES:
        u = (gt[k] | masks[k]).sum()
        if u:
            out[k] = round(float((gt[k] & masks[k]).sum()) / float(u), 3)
    ug, up = gt["window"] | gt["door"], masks["window"] | masks["door"]
    out["openings"] = round(float((ug & up).sum()) / float((ug | up).sum()), 3) if (ug | up).any() else None
    return out


def pick(dataset, n):
    """Photos where one facade dominates: much building and window, few unlabelled pixels."""
    rows = []
    if dataset == "labelme":
        for lab in sorted(glob.glob(os.path.join(ROOT, "data", "labelmefacade", "labels", "*.png"))):
            fid = os.path.basename(lab)[:-4]
            with Image.open(lab) as im:
                a = np.asarray(im.convert("RGB").resize((128, 128), Image.NEAREST))
            frac = lambda c: float(np.all(a == c, axis=-1).mean())
            b, w, v = frac(LABELME_COLORS["building"]), frac(LABELME_COLORS["window"]), frac((0, 0, 0))
            veg, car = frac((0, 128, 0)), frac((128, 0, 128))
            rows.append({"id": fid, "score": round(b + 2 * w - v - veg - car, 3), "building": round(b, 2),
                         "window": round(w, 2), "occluders": round(veg + car, 2)})
    else:
        root = hznu_root()
        for js in sorted(glob.glob(os.path.join(root, "*.json"))):
            fid = os.path.basename(js)[:-5]
            with open(js, encoding="utf-8") as fh:
                data = json.load(fh)
            rows.append({"id": fid, "score": len(hznu_polygons(data, "window")), "windows": len(hznu_polygons(data, "window"))})
    rows.sort(key=lambda r: -r["score"])
    return rows[:n]


def main(argv):
    if len(argv) < 3:
        raise SystemExit(__doc__)
    cmd = argv[1]
    if cmd == "pick":
        for r in pick(argv[2], int(argv[3])):
            print(json.dumps(r))
    elif cmd == "prep":
        path, size = prep(argv[2], _id(argv[3]))
        print("%s %dx%d" % (path, size[0], size[1]))
    elif cmd == "rect":
        ratio = None
        if "--ratio" in argv:
            num, _, den = argv[argv.index("--ratio") + 1].partition("/")
            ratio = float(num) / float(den or 1)
        face = argv[argv.index("--face") + 1] if "--face" in argv else None
        if face is not None and face not in FACES:
            raise SystemExit("--face: expected one of %s" % ", ".join(FACES))
        dst, size, r = rect(_id(argv[2]), rc.parse_corners(argv[3]), ratio, face)
        print(json.dumps({"out": dst, "size": list(size), "ratio": round(r, 3)}))
    elif cmd == "score":
        with open(argv[4], encoding="utf-8") as fh:
            pred = json.load(fh)
        print(json.dumps(score(argv[2], _id(argv[3]), pred)))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv)
