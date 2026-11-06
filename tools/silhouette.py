"""Shape and proportion check: the building's silhouette in a photo against the Rhino model's.

The facade benchmark measures elements on a flat elevation; this measures the whole form: outline,
proportions, curves. Run with the detector environment (Ultralytics, OpenCV):

    data\\venv-det\\Scripts\\python.exe tools/silhouette.py mask PHOTO OUT.png [--point x,y] [--box x0,y0,x1,y1] [--conf 0.25]
    data\\venv-det\\Scripts\\python.exe tools/silhouette.py compare MESH.json MASK.png OUT_PREFIX
        [--az A] [--el E] [--fov F] [--search]

mask     the building in the photo, from the scene model (data/det-runs/scene2, else scene11s): every building
         instance, or only the one under --point (pixels) when neighbours are in the frame.
compare  projects the model's mesh (MESH.json from tools/export_mesh.py, metres, Z up) with a
         camera at azimuth A (0 = looking from -Y, the facade's front; 90 = from +X), elevation E
         and field of view F (degrees; small = nearly parallel), scales it uniformly to the photo's
         silhouette (proportions are never stretched) and reports:
           iou      overlap of the two silhouettes (1 = same outline)
           aspect   model width/height over the photo's (1 = same proportions)
           bands    width of each tenth of the height, model over photo, top to bottom: where the
                    outline is too wide (> 1) or too narrow (< 1)
         --search tries azimuths, elevations and fields of view around the given ones and keeps the
         best; the overlay OUT_PREFIX.png shows the photo silhouette in grey, the model's in red
         outline. A photo silhouette cut by the frame edge (a tower's foot behind trees, a dome
         leaving the frame) is compared only inside the frame.
"""
import argparse
import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# scene2 first: building mask IoU 0.824 against scene11s' 0.767 on 200 photos of the scene test split
# (human building outlines), and an empty mask on 1 photo against 4.
_RUNS = [os.path.join(ROOT, "data", "det-runs", r, "weights", "best.pt") for r in ("scene2", "scene11s")]
SCENE = next((p for p in _RUNS if os.path.exists(p)), _RUNS[0])
SIDE = 256          # working resolution of the comparison (long side, pixels)
BANDS = 10


# ---------------------------------------------------------------- photo mask

OCCLUDERS = (2, 3, 4)   # scene classes that hide the building: vegetation, vehicle, person


def occluder_mask(photo, conf=0.25, weights=SCENE):
    """Boolean mask of what stands in front of buildings (trees, cars, people): the comparison
    ignores those pixels, the building behind them is unknown."""
    os.environ.setdefault("YOLO_OFFLINE", "1")
    from ultralytics import YOLO
    import cv2
    h, w = cv2.imread(photo).shape[:2]
    r = YOLO(weights).predict(photo, conf=conf, verbose=False, retina_masks=True)[0]
    mask = np.zeros((h, w), bool)
    if r.masks is not None:
        for cls, m in zip(r.boxes.cls.tolist(), r.masks.data.cpu().numpy()):
            if int(cls) in OCCLUDERS:
                mask |= cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
    return mask


def photo_mask(photo, point=None, conf=0.25, weights=SCENE):
    """Boolean mask (photo size) of the building: union of the scene model's building instances,
    or the one containing point."""
    os.environ.setdefault("YOLO_OFFLINE", "1")
    from ultralytics import YOLO
    import cv2
    img = cv2.imread(photo)
    h, w = img.shape[:2]
    r = YOLO(weights).predict(photo, conf=conf, verbose=False, retina_masks=True)[0]
    mask = np.zeros((h, w), bool)
    if r.masks is None:
        return mask
    for cls, m in zip(r.boxes.cls.tolist(), r.masks.data.cpu().numpy()):
        if int(cls) != 0:
            continue
        m = cv2.resize(m.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST).astype(bool)
        if point is None or m[point[1], point[0]]:
            mask |= m
    return mask


# ---------------------------------------------------------------- model silhouette

def load_mesh(path):
    with open(path) as f:
        d = json.load(f)
    return np.asarray(d["v"], float), np.asarray(d["f"], np.int32)


def camera(v, az, el, fov):
    """Image coordinates (x right, y down, arbitrary scale) of the vertices seen from a camera at
    azimuth az, elevation el (degrees) looking at the model's centre, field of view fov."""
    lo, hi = v.min(0), v.max(0)
    c = (lo + hi) / 2
    radius = max(np.linalg.norm(hi - lo) / 2, 1e-6)
    a, e = math.radians(az), math.radians(el)
    view = np.array([math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)])  # camera dir from centre
    dist = radius / math.tan(math.radians(max(fov, 1.0)) / 2) * 1.1
    eye = c + view * dist
    fwd = (c - eye) / np.linalg.norm(c - eye)
    right = np.cross(fwd, [0, 0, 1.0])
    if np.linalg.norm(right) < 1e-9:
        right = np.array([1.0, 0, 0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    rel = v - eye
    depth = rel @ fwd
    depth = np.maximum(depth, 1e-6)
    return np.stack([(rel @ right) / depth, -(rel @ up) / depth], 1)


def raster(xy, faces, size):
    """Silhouette of the projected triangles, cropped to its bounding box and scaled so its long
    side is size (proportions kept)."""
    import cv2
    lo, hi = xy.min(0), xy.max(0)
    span = max(hi[0] - lo[0], hi[1] - lo[1], 1e-12)
    k = (size - 1) / span
    w = int(math.ceil((hi[0] - lo[0]) * k)) + 1
    h = int(math.ceil((hi[1] - lo[1]) * k)) + 1
    pts = np.round((xy - lo) * k * 4).astype(np.int32)       # 2 bits of sub-pixel precision
    img = np.zeros((h, w), np.uint8)
    # one triangle at a time: fillPoly over many polygons fills even-odd, so overlapping
    # triangles (a window frame in front of a wall) would cancel out into holes
    for tri in pts[faces]:
        cv2.fillConvexPoly(img, tri, 1, lineType=cv2.LINE_8, shift=2)
    return img.astype(bool)


# ---------------------------------------------------------------- comparison

def crop(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def bands(mask, n=BANDS):
    """Width (pixels) of the silhouette in n equal slices of its height, top to bottom."""
    box = crop(mask)
    if box is None:
        return [0.0] * n
    x0, y0, x1, y1 = box
    out = []
    for i in range(n):
        a = y0 + (y1 - y0) * i // n
        b = max(a + 1, y0 + (y1 - y0) * (i + 1) // n)
        cols = mask[a:b].any(0)
        out.append(float(cols.sum()))
    return out


def fit(model, photo, frame):
    """Place the model silhouette over the photo's: uniform scale on the height (on the width when
    the photo silhouette touches the top or bottom of the frame and not the sides), centred on its
    bounding box; then a small search of scale and shift for the best IoU. frame: the photo area
    (all True unless the comparison is restricted)."""
    import cv2
    H, W = photo.shape
    px0, py0, px1, py1 = crop(photo)
    mh, mw = model.shape
    cut_v = py0 == 0 or py1 == H
    cut_h = px0 == 0 or px1 == W
    base = (px1 - px0) / mw if cut_v and not cut_h else (py1 - py0) / mh
    best = (-1.0, None)
    for ds in (0.9, 0.95, 1.0, 1.05, 1.1):
        s = base * ds
        sw, sh = max(1, int(round(mw * s))), max(1, int(round(mh * s)))
        m = cv2.resize(model.astype(np.uint8), (sw, sh), interpolation=cv2.INTER_NEAREST).astype(bool)
        # anchor: bottom when the photo shows the foot, top when only the foot is cut
        cx = (px0 + px1) / 2
        oy = py1 - sh if py1 < H else py0
        for dx in (-0.06, -0.03, 0, 0.03, 0.06):
            for dy in (-0.04, 0, 0.04):
                x = int(round(cx - sw / 2 + dx * sw))
                y = int(round(oy + dy * sh))
                canvas = np.zeros((H, W), bool)
                xa, ya = max(x, 0), max(y, 0)
                xb, yb = min(x + sw, W), min(y + sh, H)
                if xb <= xa or yb <= ya:
                    continue
                canvas[ya:yb, xa:xb] = m[ya - y:yb - y, xa - x:xb - x]
                inter = (canvas & photo & frame).sum()
                union = ((canvas | photo) & frame).sum()
                iou = inter / union if union else 0.0
                if iou > best[0]:
                    best = (iou, canvas)
    return best


def score(model_mask, photo_mask):
    frame = np.ones_like(photo_mask, bool)
    iou, placed = fit(model_mask, photo_mask, frame)
    pb, mb = crop(photo_mask), crop(placed)
    aspect = ((mb[2] - mb[0]) / (mb[3] - mb[1])) / ((pb[2] - pb[0]) / (pb[3] - pb[1]))
    wp, wm = bands(photo_mask), bands(placed)
    ratio = [round(m / p, 2) if p else None for m, p in zip(wm, wp)]
    return {"iou": round(float(iou), 3), "aspect": round(float(aspect), 2), "bands": ratio}, placed


def small(mask, side=SIDE):
    import cv2
    h, w = mask.shape
    k = side / max(h, w)
    return cv2.resize(mask.astype(np.uint8), (max(1, int(w * k)), max(1, int(h * k))),
                      interpolation=cv2.INTER_NEAREST).astype(bool)


def compare(mesh, mask_png, az=0.0, el=5.0, fov=30.0, search=False):
    import cv2
    v, f = load_mesh(mesh)
    photo = small(cv2.imread(mask_png, cv2.IMREAD_GRAYSCALE) > 127)
    tries = [(az, el, fov)]
    if search:
        tries = [(az + da, el + de, fv) for da in range(-40, 41, 10) for de in (-10, -5, 0, 5, 10, 20)
                 for fv in (10, 30, 50)]
    best = None
    for a, e, fv in tries:
        sil = raster(camera(v, a, e, fv), f, SIDE)
        s, placed = score(sil, photo)
        if best is None or s["iou"] > best[0]["iou"]:
            best = (s, placed, (a, e, fv))
    s, placed, (a, e, fv) = best
    if search:  # refine around the best
        for da in (-5, 0, 5):
            for de in (-2.5, 0, 2.5):
                sil = raster(camera(v, a + da, e + de, fv), f, SIDE)
                s2, p2 = score(sil, photo)
                if s2["iou"] > s["iou"]:
                    s, placed, best_cam = s2, p2, (a + da, e + de, fv)
                    best = (s, placed, best_cam)
        s, placed, (a, e, fv) = best
    s["camera"] = {"az": a, "el": e, "fov": fv}
    return s, photo, placed


def compare_calibrated(mesh, mask_png, calib):
    """The model seen by the camera solved from the photo (tools/photo3d.py), in the photo's own
    pixels: no fitting, so the score is the model's error alone."""
    import cv2
    import photo3d
    v, f = load_mesh(mesh)
    photo = cv2.imread(mask_png, cv2.IMREAD_GRAYSCALE) > 127
    H, W = photo.shape
    cam = dict(calib["camera"])
    k = W / cam["image"][0]                      # mask and reading at different sizes
    uv = photo3d.project(cam, v) * k
    img = np.zeros((H, W), np.uint8)
    pts = np.round(np.nan_to_num(uv, nan=-1e5) * 4).clip(-2**28, 2**28).astype(np.int32)
    for tri in pts[f]:
        cv2.fillConvexPoly(img, tri, 1, lineType=cv2.LINE_8, shift=2)
    model = img.astype(bool)
    occ_png = os.path.splitext(mask_png)[0] + ".occ.png"
    seen = np.ones_like(photo)
    if os.path.exists(occ_png):                  # trees, cars, people: the building there is unknown
        seen = ~(cv2.imread(occ_png, cv2.IMREAD_GRAYSCALE) > 127)
    model_all = model
    photo, model = photo & seen, model & seen
    inter, union = (model & photo).sum(), (model | photo).sum()
    rows = crop(photo)
    y0, y1 = rows[1], rows[3]
    ratio = []
    for i in range(BANDS):
        a = y0 + (y1 - y0) * i // BANDS
        b = max(a + 1, y0 + (y1 - y0) * (i + 1) // BANDS)
        p, m = photo[a:b].any(0).sum(), model[a:b].any(0).sum()
        ratio.append(round(float(m / p), 2) if p else None)
    s = {"iou": round(float(inter / union), 3) if union else 0.0, "bands": ratio,
         "extra": round(float((model & ~photo).sum() / max(photo.sum(), 1)), 3),
         "missing": round(float((photo & ~model).sum() / max(photo.sum(), 1)), 3),
         "hidden": round(float((~seen).mean()), 3)}
    return s, small(photo, max(H, W)), small(model_all, max(H, W))


def overlay(photo, placed, out):
    import cv2
    img = np.full(photo.shape + (3,), 255, np.uint8)
    img[photo] = (190, 190, 190)
    edge = placed & ~cv2.erode(placed.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    img[edge] = (0, 0, 220)
    cv2.imwrite(out, cv2.resize(img, (img.shape[1] * 2, img.shape[0] * 2), interpolation=cv2.INTER_NEAREST))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mask")
    m.add_argument("photo")
    m.add_argument("out")
    m.add_argument("--point")
    m.add_argument("--box", help="x0,y0,x1,y1: keep only this rectangle (neighbours fused with the building)")
    m.add_argument("--conf", type=float, default=0.25)
    c = sub.add_parser("compare")
    c.add_argument("mesh")
    c.add_argument("mask")
    c.add_argument("out")
    c.add_argument("--az", type=float, default=0.0)
    c.add_argument("--el", type=float, default=5.0)
    c.add_argument("--fov", type=float, default=30.0)
    c.add_argument("--search", action="store_true")
    c.add_argument("--calib", help="camera solved by tools/photo3d.py: compare in the photo's own frame, no fitting")
    a = ap.parse_args(argv)
    import cv2
    if a.cmd == "mask":
        pt = tuple(int(t) for t in a.point.split(",")) if a.point else None
        mask = photo_mask(a.photo, pt, a.conf)
        if a.box:
            x0, y0, x1, y1 = (int(t) for t in a.box.split(","))
            keep = np.zeros_like(mask)
            keep[y0:y1, x0:x1] = True
            mask &= keep
        cv2.imwrite(a.out, mask.astype(np.uint8) * 255)
        occ = occluder_mask(a.photo, a.conf) & ~mask
        cv2.imwrite(os.path.splitext(a.out)[0] + ".occ.png", occ.astype(np.uint8) * 255)
        print(json.dumps({"pixels": int(mask.sum()), "box": [int(t) for t in crop(mask)] if mask.any() else None}))
        return 0
    if a.calib:
        with open(a.calib) as fh:
            s, photo, placed = compare_calibrated(a.mesh, a.mask, json.load(fh))
    else:
        s, photo, placed = compare(a.mesh, a.mask, a.az, a.el, a.fov, a.search)
    overlay(photo, placed, a.out + ".png")
    print(json.dumps(s))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
