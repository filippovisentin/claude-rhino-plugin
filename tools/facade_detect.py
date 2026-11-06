"""Runtime facade detector used by the plugin's detect_facade tool: any photo -> px facade draft.

    python tools/facade_detect.py detect-image PHOTO WEIGHTS CONF

WEIGHTS is one .pt file or several joined by os.pathsep (their boxes are fused). Needs the
detector environment (Ultralytics, numpy, Pillow). Training and benchmarks live in tools/dev/
(facade_yolo.py re-exports everything here).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# CMP's own classes; rustic and quoin are not annotated there.
NAMES = ["window", "door", "shop", "balcony", "cornice", "molding", "pillar", "sill", "blind", "deco"]

REVIEW = ("Detector draft in this image's pixels. Reliable: window, sill, cornice, molding, balcony, "
          "blind; arch and round window shapes, pediments (cornice tri over an opening, else k pediment) "
          "and finials come from a model trained on monuments: keep them where the photo agrees. Check "
          "yourself: door (weakest class), shop, pillar, deco, set h; px is the box around the detected "
          "elements: move it to the facade's own corners (the wall's edges and the roofline usually lie "
          "a little outside it; drop neighbours' windows), merge duplicates, add rustic/quoin. "
          "palette: colours read off the photo (median, exposure-corrected); check it before passing it on.")


# Element order in a draft: CMP's classes, then what the parts model adds.
ORDER = NAMES + ["pediment", "finial"]


def _iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / float(union) if union > 0 else 0.0


def _hood(b, openings):
    """A pediment box that crowns an opening: just above it, about as wide."""
    bh = b[3] - b[1]
    for o in openings:
        ow = o["box"][2] - o["box"][0]
        overlap = min(b[2], o["box"][2]) - max(b[0], o["box"][0])
        gap = o["box"][1] - b[3]
        if overlap >= 0.6 * ow and b[2] - b[0] <= 1.8 * ow and -0.3 * bh <= gap <= 0.6 * bh:
            return True
    return False


def draft_elements(dets, w, h, conf=0.25):
    """Detections [(class, conf, x0, y0, x1, y1) px] -> px spec elements, in the spec's own words.
    The parts model's extra classes become shapes and elements the builder knows: an arch or an
    oculus shapes the opening under it (or is an opening of that shape when none is there), a
    triangular pediment just above an opening is its hood (cornice tri) and otherwise a pediment,
    a segmental one a curved hood (cornice seg), a finial a spire."""
    from facade_regular import dedupe
    clip = lambda b: [max(0, round(b[0])), max(0, round(b[1])), min(w, round(b[2])), min(h, round(b[3]))]
    dets = [(k, c, clip(b)) for k, c, *b in dedupe(dets) if c >= conf]
    dets = [d for d in dets if d[2][2] > d[2][0] and d[2][3] > d[2][1]]
    els = [{"k": k, "box": b} for k, c, b in dets if k in NAMES]
    openings = [e for e in els if e["k"] in ("window", "door", "shop")]
    for k, c, b in sorted((d for d in dets if d[0] in ("arch", "oculus")), key=lambda d: -d[1]):
        shape = "arch" if k == "arch" else "round"
        cand = [e for e in openings if "shape" not in e and (k == "arch" or e["k"] == "window") and _iou(e["box"], b) >= 0.5]
        if cand:
            max(cand, key=lambda e: _iou(e["box"], b))["shape"] = shape
        else:
            els.append({"k": "window", "box": b, "shape": shape})
    for k, c, b in dets:
        if k == "finial":
            els.append({"k": "finial", "box": b, "shape": "spire"})
        elif k == "pediment_seg":
            els.append({"k": "cornice", "box": b, "shape": "seg"})
        elif k == "pediment":
            els.append({"k": "cornice", "box": b, "shape": "tri"} if _hood(b, openings) else {"k": "pediment", "box": b})
    els.sort(key=lambda e: (ORDER.index(e["k"]), e["box"][1] // 20, e["box"][0]))
    return els


def fuse_boxes(per_model, weights=None, iou=0.55, mode="avg"):
    """Weighted boxes fusion (Solovyev et al. 2021) of several models' detections on one photo.
    per_model: one list of (class, conf, x0, y0, x1, y1) per model. Boxes of the same class that
    overlap (IoU > iou with the cluster's fused box) are averaged, weighted by confidence.
    mode avg: a box found by only some of the models keeps a proportionally lower confidence, so
    the models must agree to stay confident. mode max: the cluster keeps its most confident
    member's confidence (over the largest model weight), so one model alone is enough."""
    weights = list(weights or [1.0] * len(per_model))
    total = float(sum(weights))
    boxes = sorted(((k, c * wt, list(b)) for dets, wt in zip(per_model, weights) for k, c, *b in dets),
                   key=lambda d: -d[1])
    clusters = []   # [class, [(score, box)], fused box]
    for k, s, b in boxes:
        best, best_iou = None, iou
        for cl in clusters:
            if cl[0] == k:
                v = _iou(cl[2], b)
                if v > best_iou:
                    best, best_iou = cl, v
        if best is None:
            clusters.append([k, [(s, b)], b])
        else:
            best[1].append((s, b))
            ssum = sum(x[0] for x in best[1])
            best[2] = [sum(x[0] * x[1][i] for x in best[1]) / ssum for i in range(4)]
    out = []
    for k, members, b in clusters:
        if mode == "max":
            score = max(m[0] for m in members) / max(weights)
        else:
            score = sum(m[0] for m in members) / len(members) * min(len(members), len(per_model)) / total
        out.append((k, min(1.0, score), *b))
    return out


_MODELS = {}


def pick_device(env=os.environ, cuda=None):
    """GPU 0 when torch sees one, else "cpu". RHINO_FACADE_DEVICE=cpu forces the CPU; =cuda only
    asks for the GPU and still falls back. Passed to every predict, because Ultralytics would
    otherwise reuse the device stored in the weights (GPU 0 from training) and fail without one."""
    if cuda is None:
        import torch
        # is_available() can stay True with every GPU hidden (CUDA_VISIBLE_DEVICES=""): count them too
        cuda = torch.cuda.is_available() and torch.cuda.device_count() > 0
    if env.get("RHINO_FACADE_DEVICE") == "cpu" or not cuda:
        return "cpu"
    return 0


def predict(weights, path, conf=0.25, model_weights=None, mode="max"):
    """Detections [(class, conf, x0, y0, x1, y1) px] and (w, h) for one photo. weights is one .pt
    path, or several joined by os.pathsep (or a list): then every model runs at a lower
    confidence and their boxes are fused (fuse_boxes) before the threshold. The first model is
    the main one and weighs 2, the others 1, unless model_weights says otherwise.
    Measured (tools/ensemble_report.py, report4's unseen photos): parts2m + parts11s, max, 2:1
    against parts2m alone: mAP50 CMP 0.742 -> 0.764, modern 0.982 = 0.982, Oxford 0.813 -> 0.807,
    monuments 0.988 -> 0.999; pixel IoU vs Claude's 0.516 on CMP 0.619 -> 0.629 at conf 0.25.
    Plain WBF (mode avg) scored higher on CMP but was unstable: its mean over cluster members
    falls as low-confidence boxes join, which moved Oxford between 0.76 and 0.85."""
    from ultralytics import YOLO
    paths = weights if isinstance(weights, (list, tuple)) else str(weights).split(os.pathsep)
    paths = [p for p in paths if p]
    per, w, h = [], None, None
    dev = pick_device()
    for p in paths:
        if p not in _MODELS:
            _MODELS[p] = YOLO(p)
        r = _MODELS[p].predict(path, conf=conf if len(paths) == 1 else min(conf, 0.05) / 2, device=dev,
                               verbose=False)[0]
        h, w = r.orig_shape
        per.append([(r.names[int(c)], float(s), *map(float, b))
                    for c, s, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxy.tolist())])
    if len(per) == 1:
        return per[0], (w, h)
    mw = model_weights or [2.0] + [1.0] * (len(per) - 1)
    dets = [d for d in fuse_boxes(per, mw, mode=mode) if d[1] >= conf]
    return dets, (w, h)


def facade_px(els, w, h):
    """First guess of the facade's px corners: the box around the detected elements, else the
    whole photo. Measured on all 606 CMP photos against their facade outlines (box IoU): 0.865
    against 0.810 for the whole photo, outlines under 0.7 on 11 % of photos against 26 %. The
    scene model's building box scored 0.844, and margins or snapping sides to it changed less
    than 0.004, so the plain box stays. Neighbours' windows in a street photo widen it."""
    if not els:
        return [0, 0, w, h]
    return [min(e["box"][0] for e in els), min(e["box"][1] for e in els),
            max(e["box"][2] for e in els), max(e["box"][3] for e in els)]


def detect_image(path, weights, conf=0.25):
    """Any photo -> {img, els, review}: a px facade draft for Claude to correct, sorted by class
    and position so rows read in order. weights: one model, or several joined by os.pathsep."""
    dets, (w, h) = predict(weights, path, conf)
    els = draft_elements(dets, w, h, conf)
    out = {"img": [w, h], "px": facade_px(els, w, h), "els": els, "review": REVIEW,
           "device": "cpu" if pick_device() == "cpu" else "cuda"}
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


def main(argv):
    if argv[:1] == ["detect-image"] and len(argv) == 4:
        conf = float(argv[3])
        if not 0.05 <= conf <= 0.95:
            raise SystemExit("conf must be 0.05-0.95")
        print(json.dumps(detect_image(argv[1], argv[2], conf), separators=(",", ":")))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
