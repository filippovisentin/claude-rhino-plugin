"""Local facade detector: CMP Facade DB -> YOLO dataset, and detections -> px facade spec.

    python tools/facade_yolo.py dataset [hznu] [cfp]  # writes data/yolo/{images,labels}/{train,val,test} + cmp.yaml
    python tools/facade_yolo.py spec ID WEIGHTS    # runs the detector on one CMP photo, prints a px spec
    python tools/facade_yolo.py detect-image PATH WEIGHTS CONF   # any photo -> px draft (used by detect_facade)
    python tools/facade_yolo.py compare WEIGHTS [CONF]  # detector vs Claude's blind readings on the test split

The test split is every CMP photo Claude has already read blind (data/work/<id>.pred.json), so
detector and Claude are scored on the same photos with facade_bench. Those photos never enter
training. CMP is CC BY-SA: a model trained on it is for personal and study use; share it under
the same licence.
"""
import json
import os
import random
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facade_bench as FB  # noqa: E402

OUT = os.path.join(FB.ROOT, "data", "yolo")
# CMP's own classes; rustic and quoin are not annotated there.
NAMES = ["window", "door", "shop", "balcony", "cornice", "molding", "pillar", "sill", "blind", "deco"]


def test_ids(hznu=False):
    """Photos Claude read blind: CMP ones, plus hznu ones (c_/d_) when hznu is on."""
    ids = []
    for f in sorted(os.listdir(FB.WORK)):
        fid = f[:-len(".pred.json")] if f.endswith(".pred.json") else None
        if fid and (FB.ID_RE.match(fid) or (hznu and fid in HZNU_SET())):
            ids.append(fid)
    return ids


def HZNU_SET():
    return set(hznu_ids())


def yolo_lines(objs):
    """Annotation objects (normalised, y down) -> YOLO 'cls cx cy w h' lines."""
    out = []
    for k, x0, y0, x1, y1 in objs:
        if k not in NAMES:
            continue
        x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
        if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4:
            continue
        out.append("%d %.6f %.6f %.6f %.6f" % (NAMES.index(k), (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0))
    return out


HZNU = os.path.join(FB.ROOT, "data", "hznu", "all_adjust_zhedang")
HZNU_CLASSES = ("window", "door")   # all hznu labels; its other facade parts are unlabelled


def hznu_ids():
    return sorted(f[:-5] for f in os.listdir(HZNU) if f.endswith(".json")) if os.path.isdir(HZNU) else []


def hznu_objs(fid):
    """hznu polygons (pixels of the photo) -> normalised (class, x0, y0, x1, y1) boxes."""
    from PIL import Image
    with open(os.path.join(HZNU, fid + ".json"), encoding="utf-8") as fh:
        data = json.load(fh)
    with Image.open(os.path.join(HZNU, fid + ".jpg")) as im:
        w, h = im.size
    out = []
    for sh in data.get("shapes", []):
        pts = sh.get("points") or []
        if sh.get("label") in HZNU_CLASSES and len(pts) >= 2:
            xs, ys = [float(q[0]) for q in pts], [float(q[1]) for q in pts]
            out.append((sh["label"], min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h))
    return out


CFP = os.path.join(FB.ROOT, "data", "cfp", "raw_data")   # Wang et al. 2024, street views; no licence stated


def cfp_entries():
    """{cfp_NNNN: path without extension}, numbered over the sorted original names."""
    if not os.path.isdir(CFP):
        return {}
    names = sorted(f[:-5] for f in os.listdir(CFP) if f.endswith(".json"))
    return dict(("cfp_%04d" % i, os.path.join(CFP, n)) for i, n in enumerate(names))


def labelme_objs(json_path, img_path, classes=HZNU_CLASSES):
    """LabelMe polygons/rectangles (photo pixels) -> normalised (class, x0, y0, x1, y1) boxes."""
    from PIL import Image
    with open(json_path, encoding="utf-8") as fh:
        data = json.load(fh)
    with Image.open(img_path) as im:
        w, h = im.size
    out = []
    for sh in data.get("shapes", []):
        pts = sh.get("points") or []
        if sh.get("label") in classes and sh.get("shape_type", "polygon") in ("polygon", "rectangle") and len(pts) >= 2:
            xs, ys = [float(q[0]) for q in pts], [float(q[1]) for q in pts]
            out.append((sh["label"], min(xs) / w, min(ys) / h, max(xs) / w, max(ys) / h))
    return out


def _image(path):
    return path + ".jpg" if os.path.exists(path + ".jpg") else path + ".JPG"


def _copy_small(src, dst, side=1600):
    """Copies a photo, shrunk so its long side is at most side px (YOLO trains at 1024)."""
    from PIL import Image
    with Image.open(src) as im:
        if max(im.size) > side:
            im = im.copy()
            im.thumbnail((side, side))
        im.convert("RGB").save(dst, quality=92)


def dataset(val_frac=0.1, seed=7, hznu=False, cfp=False):
    out = OUT + ("-all" if cfp else "-modern" if hznu else "")
    hznu = hznu or cfp
    cfp_map = cfp_entries() if cfp else {}
    test = set(test_ids(hznu))
    rest = [i for i in FB.all_ids() if i not in test]
    random.Random(seed).shuffle(rest)
    n_val = int(len(rest) * val_frac)
    split = {"val": rest[:n_val], "train": rest[n_val:], "test": sorted(test)}
    if hznu:   # modern Hangzhou facades: windows and doors only
        h_test = set(i for i in test if not FB.ID_RE.match(i))
        h_rest = [i for i in hznu_ids() if i not in h_test]
        random.Random(seed).shuffle(h_rest)
        n = int(len(h_rest) * val_frac)
        split["val"] += h_rest[:n]
        split["train"] += h_rest[n:]
        split["test_hznu"] = sorted(h_test) + h_rest[:n]   # never trained on (val only picks the epoch)
    if cfp:   # street views from Osaka, Tokyo, Toronto, Shanghai: windows and doors only
        c_ids = sorted(cfp_map)
        random.Random(seed).shuffle(c_ids)
        n = int(len(c_ids) * val_frac)
        split["test_cfp"] = sorted(c_ids[:n])
        split["val"] += c_ids[n:2 * n]
        split["train"] += c_ids[2 * n:]
    if os.path.isdir(out):
        shutil.rmtree(out)
    for name, ids in split.items():
        if name == "test_hznu":
            continue   # listed below: its photos already sit in test and val
        os.makedirs(os.path.join(out, "images", name))
        os.makedirs(os.path.join(out, "labels", name))
        for fid in ids:
            if FB.ID_RE.match(fid):
                _, objs = FB.read_annotation(fid)
                shutil.copyfile(FB._paths(fid) + ".jpg", os.path.join(out, "images", name, fid + ".jpg"))
            elif fid in cfp_map:
                objs = labelme_objs(cfp_map[fid] + ".json", _image(cfp_map[fid]))
                _copy_small(_image(cfp_map[fid]), os.path.join(out, "images", name, fid + ".jpg"))
            else:
                objs = hznu_objs(fid)
                _copy_small(os.path.join(HZNU, fid + ".jpg"), os.path.join(out, "images", name, fid + ".jpg"))
            with open(os.path.join(out, "labels", name, fid + ".txt"), "w") as fh:
                fh.write("\n".join(yolo_lines(objs)) + "\n")
    _yaml(out, "cmp.yaml", "images/test")
    # per-source test sets, as image lists, so every model is scored on the same photos
    where = dict((fid, name) for name, ids in split.items() if name != "test_hznu" for fid in ids)
    groups = {"cmp": [i for i in split["test"] if FB.ID_RE.match(i)]}
    if hznu:
        groups["hznu"] = split["test_hznu"]
    if cfp:
        groups["cfp"] = split["test_cfp"]
    for g, ids in groups.items():
        with open(os.path.join(out, "test_%s.txt" % g), "w") as fh:
            fh.write("".join("%s/images/%s/%s.jpg\n" % (out.replace("\\", "/"), where[i], i) for i in ids))
        _yaml(out, "test_%s.yaml" % g, "test_%s.txt" % g)
    return dict((k, len(v)) for k, v in split.items())


def _yaml(out, name, test):
    with open(os.path.join(out, name), "w") as fh:
        fh.write("path: %s\ntrain: images/train\nval: images/val\ntest: %s\nnames:\n" % (out.replace("\\", "/"), test))
        for i, n in enumerate(NAMES):
            fh.write("  %d: %s\n" % (i, n))


def detections_to_spec(dets, img_w, img_h, name, conf=0.25, h=12.0):
    """[(class, conf, x0, y0, x1, y1) in px] -> px facade spec over the whole photo (h in metres)."""
    els = []
    for k, c, x0, y0, x1, y1 in dets:
        x0, y0, x1, y1 = max(0, round(x0)), max(0, round(y0)), min(img_w, round(x1)), min(img_h, round(y1))
        if c >= conf and k in NAMES and x1 > x0 and y1 > y0:
            els.append({"k": k, "box": [x0, y0, x1, y1]})
    return {"units": "m", "layer": "DET " + name, "clear": True, "parts": [
        {"type": "facade", "name": name, "h": h, "px": [0, 0, img_w, img_h], "els": els}]}


def detect(fid, weights, conf=0.25):
    """Runs on data/work/<id>.jpg, the photo Claude read, so the px boxes share its pixels."""
    from ultralytics import YOLO
    path = os.path.join(FB.WORK, fid + ".jpg")
    if not os.path.exists(path):
        FB.prep(fid)
    r = YOLO(weights).predict(path, conf=conf, verbose=False)[0]
    h, w = r.orig_shape
    dets = [(r.names[int(c)], float(p), *map(float, b))
            for c, p, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]
    return detections_to_spec(dets, w, h, fid, conf)


REVIEW = ("Detector draft in this image's pixels. Reliable: window, sill, cornice, molding, balcony, "
          "blind, deco. Check yourself: door, shop, pillar (often missed or wrong), set h and px "
          "(the facade's own corners; the draft spans the whole image), merge duplicates, add rustic/quoin. "
          "palette: colours read off the photo (median, exposure-corrected); check it before passing it on.")


def detect_image(path, weights, conf=0.25):
    """Any photo -> {img, els, review}: a px facade draft for Claude to correct, sorted by class
    and position so rows read in order."""
    from ultralytics import YOLO
    r = YOLO(weights).predict(path, conf=conf, verbose=False)[0]
    h, w = r.orig_shape
    dets = [(r.names[int(c)], float(p), *map(float, b))
            for c, p, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]
    from facade_regular import dedupe
    els = detections_to_spec(dedupe(dets), w, h, "draft", conf)["parts"][0]["els"]
    els.sort(key=lambda e: (NAMES.index(e["k"]), e["box"][1] // 20, e["box"][0]))
    out = {"img": [w, h], "els": els, "review": REVIEW}
    pal = sample_palette(path, els)
    if pal:
        out["palette"] = pal
    return out


PALETTE_FROM = {"glass": ("window",), "shutters": ("blind",), "doors": ("door",),
                "trim": ("molding", "cornice", "sill", "pillar")}


def dominant(px, step=24):
    """The commonest colour: pixels binned on a coarse RGB grid, the fullest bin averaged. The
    wall is the largest even surface, so this ignores roof tiles, shadows and sky at the edges."""
    import numpy as np
    q = (px // step).astype(np.int32)
    keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    best = px[keys == vals[counts.argmax()]]
    return "#%02x%02x%02x" % tuple(int(x) for x in best.mean(axis=0))


def sample_palette(path, els):
    """Median colours read off the photo: the wall from the facade area outside every box, the
    rest from the middle half of their boxes. Keys follow the spec's palette."""
    import numpy as np
    from PIL import Image
    with Image.open(path) as im:
        a = np.asarray(im.convert("RGB"))
    hgt, wid = a.shape[:2]
    hexc = lambda px: "#%02x%02x%02x" % tuple(int(x) for x in np.median(px, axis=0))
    out = {}
    if els:
        x0 = max(0, min(e["box"][0] for e in els)); x1 = min(wid, max(e["box"][2] for e in els))
        y0 = max(0, min(e["box"][1] for e in els)); y1 = min(hgt, max(e["box"][3] for e in els))
        mask = np.zeros((hgt, wid), bool)
        mask[y0:y1, x0:x1] = True
        for e in els:
            bx0, by0, bx1, by1 = e["box"]
            mask[by0:by1, bx0:bx1] = False
        if mask.sum() > 500:
            out["wall"] = dominant(a[mask])
    for key, ks in PALETTE_FROM.items():
        px = []
        for e in els:
            if e["k"] in ks:
                bx0, by0, bx1, by1 = e["box"]
                qw, qh = (bx1 - bx0) // 4, (by1 - by0) // 4
                px.append(a[by0 + qh:by1 - qh, bx0 + qw:bx1 - qw].reshape(-1, 3))
        px = np.concatenate(px) if px else np.zeros((0, 3))
        if len(px) > 50:
            out[key] = hexc(px)
    return _expose(out)


def _expose(pal, target=0.78, most=1.6):
    """Overcast photos and Rhino's shading both darken: when the wall reads darker than target
    luminance, every colour is brightened by the same factor (at most most), keeping their ratios."""
    if "wall" not in pal:
        return pal
    rgb = lambda c: [int(c[i:i + 2], 16) for i in (1, 3, 5)]
    lum = sum(w * v for w, v in zip((0.2126, 0.7152, 0.0722), rgb(pal["wall"]))) / 255.0
    k = min(most, target / lum) if 0 < lum < target else 1.0
    return dict((key, "#%02x%02x%02x" % tuple(min(255, int(v * k)) for v in rgb(c))) for key, c in pal.items())


def compare(weights, conf=0.25):
    """mIoU per test photo and mean IoU per class, detector against Claude's readings."""
    from ultralytics import YOLO
    model = YOLO(weights)
    rows, per = [], {"det": {}, "claude": {}}
    for fid in test_ids():
        path = os.path.join(FB.WORK, fid + ".jpg")
        r = model.predict(path, conf=conf, verbose=False)[0]
        h, w = r.orig_shape
        dets = [(r.names[int(c)], float(p), *map(float, b))
                for c, p, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist())]
        det = FB.score_px(fid, detections_to_spec(dets, w, h, fid, conf))
        cla = FB.score_px(fid, FB._load(os.path.join(FB.WORK, fid + ".pred.json")))
        rows.append((fid, det["mIoU"], cla["mIoU"], det["openings_IoU"], cla["openings_IoU"]))
        for who, sc in (("det", det), ("claude", cla)):
            for k, v in sc["per_class"].items():
                if v is not None:
                    per[who].setdefault(k, []).append(v)
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None
    print("%-10s %6s %6s %8s %8s" % ("photo", "det", "claude", "det_open", "cl_open"))
    for row in rows:
        print("%-10s %6s %6s %8s %8s" % row)
    print("%-10s %6s %6s %8s %8s" % ("MEAN", mean([r[1] for r in rows]), mean([r[2] for r in rows]),
                                      mean([r[3] for r in rows]), mean([r[4] for r in rows])))
    print("\nper class   det  claude")
    for k in NAMES:
        print("%-9s %6s %6s" % (k, mean(per["det"].get(k, [])), mean(per["claude"].get(k, []))))


def main(argv):
    if argv[:1] == ["dataset"]:
        print(json.dumps(dataset(hznu="hznu" in argv[1:], cfp="cfp" in argv[1:])))
    elif argv[:1] == ["spec"] and len(argv) == 3:
        print(json.dumps(detect(argv[1], argv[2])))
    elif argv[:1] == ["detect-image"] and len(argv) == 4:
        conf = float(argv[3])
        if not 0.05 <= conf <= 0.95:
            raise SystemExit("conf must be 0.05-0.95")
        print(json.dumps(detect_image(argv[1], argv[2], conf), separators=(",", ":")))
    elif argv[:1] == ["compare"] and len(argv) in (2, 3):
        compare(argv[1], float(argv[2]) if len(argv) == 3 else 0.25)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
