"""Refines a facade spec read off a photo, using the photo itself. No tokens: pure numpy.

  python tools/facade_refine.py IMAGE SPEC OUT [--find window,door] [--thr 0.6] [--snap]

IMAGE is the photo the boxes were read from (same pixels: use the one Claude looked at).
SPEC holds one facade part with "px". Two steps:

  find  every box listed for a class in --find is a template: matches elsewhere in the facade
        (normalised cross-correlation) become new elements of that class. Catches the shaded,
        partly hidden and simply overlooked copies a reader misses.
  snap  (opt-in; measured to hurt on CMP, whose boxes include the window surround while the
        strongest edge is often the glass) each opening edge moves up to ~15% of the box size to the strongest image edge
        parallel to it, which fixes the few-pixel slop of reading coordinates by eye.

Prints one line: {"added": n, "snapped": n, "els": n}. OUT is plain JSON for rhinospec.run.

EXPERIMENTAL, not part of the rhino-model workflow. Measured on four CMP photos (window IoU of a
careful reading -> after refine at --thr 0.7): b0101 0.87->0.88, b0304 0.59->0.56,
b0290 0.77->0.77, b0161 0.80->0.54. A careful reading already finds the copies NCC can see, so
what NCC adds is mostly false positives; snapping moved boxes onto the glass instead of the
annotated surround. Kept for photos with many identical, unoccluded windows.
"""
import json
import os
import sys

import numpy as np
from PIL import Image

SNAP_CLASSES = ("window", "door", "shop", "balcony")
MAX_MATCHES = 300


def load_gray(path):
    with Image.open(path) as im:
        return np.asarray(im.convert("L"), dtype=np.float64)


def gradients(img):
    """|d/dx| and |d/dy|, same shape as img (last column / row zero)."""
    gx = np.zeros_like(img)
    gy = np.zeros_like(img)
    gx[:, :-1] = np.abs(np.diff(img, axis=1))
    gy[:-1, :] = np.abs(np.diff(img, axis=0))
    return gx, gy


def snap_box(box, gx, gy, frac=0.15, min_r=2):
    """Moves each edge of [x0, y0, x1, y1] to the strongest parallel edge nearby."""
    H, W = gx.shape
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    if x1 - x0 < 4 or y1 - y0 < 4:
        return list(box)
    rx = max(min_r, int((x1 - x0) * frac))
    ry = max(min_r, int((y1 - y0) * frac))
    # Sample edges on their middle 80% so corners and neighbours weigh less.
    ya, yb = y0 + (y1 - y0) // 10, y1 - (y1 - y0) // 10
    xa, xb = x0 + (x1 - x0) // 10, x1 - (x1 - x0) // 10

    def best(center, r, strength, lo, hi):
        cands = [c for c in range(center - r, center + r + 1) if lo <= c < hi]
        if not cands:
            return center
        scores = [strength(c) for c in cands]
        top = max(scores)
        # Prefer the original position unless an edge is clearly stronger.
        return center if strength(center) >= 0.85 * top or top <= 0 else cands[scores.index(top)]

    col = lambda c: gx[max(ya, 0):min(yb, H), c].mean() if 0 <= c < W else 0.0
    row = lambda r: gy[r, max(xa, 0):min(xb, W)].mean() if 0 <= r < H else 0.0
    nx0 = best(x0, rx, col, 0, W)
    nx1 = best(x1 - 1, rx, col, 0, W) + 1
    ny0 = best(y0, ry, row, 0, H)
    ny1 = best(y1 - 1, ry, row, 0, H) + 1
    if nx1 - nx0 < 0.5 * (x1 - x0) or ny1 - ny0 < 0.5 * (y1 - y0):
        return list(box)          # a collapse means the edges were noise: keep the reading
    return [int(nx0), int(ny0), int(nx1), int(ny1)]


def ncc_map(img, tpl):
    """Normalised cross-correlation of tpl over img (valid positions), via FFT."""
    H, W = img.shape
    h, w = tpl.shape
    t = tpl - tpl.mean()
    tn = np.sqrt((t * t).sum())
    if tn < 1e-6 or h > H or w > W:
        return None
    corr = np.fft.irfft2(np.fft.rfft2(img) * np.conj(np.fft.rfft2(t, s=img.shape)), s=img.shape)
    corr = corr[: H - h + 1, : W - w + 1]
    ii = np.pad(img, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    ii2 = np.pad(img * img, ((1, 0), (1, 0))).cumsum(0).cumsum(1)
    win = lambda a: a[h:, w:] - a[:-h, w:] - a[h:, :-w] + a[:-h, :-w]
    s, s2 = win(ii), win(ii2)
    var = np.maximum(s2 - s * s / (h * w), 0)
    ncc = corr / (np.sqrt(var) * tn + 1e-9)
    # Flat areas (plain wall, sky) have near-zero variance, which blows the ratio up into false
    # matches: require at least a quarter of the template's contrast.
    tpl_std = tn / np.sqrt(h * w)
    ncc[np.sqrt(var / (h * w)) < 0.25 * tpl_std] = 0.0
    return ncc


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / float(union) if union > 0 else 0.0


def aligned(bx, others, tol=0.2):
    """Facades are regular: a real copy shares a row (top and bottom) or a column (left and right)
    with a known element of its class. This rejects most look-alike texture."""
    w, h = bx[2] - bx[0], bx[3] - bx[1]
    for t in others:
        if abs(bx[1] - t[1]) <= tol * h and abs(bx[3] - t[3]) <= tol * h:
            return True
        if abs(bx[0] - t[0]) <= tol * w and abs(bx[2] - t[2]) <= tol * w:
            return True
    return False


def find_matches(img, tpl_box, region, thr, taken):
    """Boxes like tpl_box inside region whose NCC beats thr, aligned with a taken box of the same
    class and not overlapping any."""
    x0, y0, x1, y1 = [int(round(v)) for v in tpl_box]
    rx0, ry0, rx1, ry1 = [int(round(v)) for v in region]
    sub = img[max(ry0, 0):ry1, max(rx0, 0):rx1]
    tpl = img[y0:y1, x0:x1]
    if tpl.size == 0 or tpl.shape[0] < 6 or tpl.shape[1] < 6:
        return []
    m = ncc_map(sub, tpl)
    if m is None:
        return []
    h, w = tpl.shape
    found = []
    m = m.copy()
    while len(found) < MAX_MATCHES:
        j, i = (int(v) for v in np.unravel_index(np.argmax(m), m.shape))
        if m[j, i] < thr:
            break
        bx = [i + max(rx0, 0), j + max(ry0, 0), i + max(rx0, 0) + w, j + max(ry0, 0) + h]
        m[max(j - h // 2, 0):j + h // 2 + 1, max(i - w // 2, 0):i + w // 2 + 1] = -1
        if all(iou(bx, t) < 0.2 for t in taken + found) and aligned(bx, taken + found):
            found.append(bx)
    return found


def expand(el):
    """A px element (grid or xs/ys) -> list of [x0, y0, x1, y1] boxes."""
    from facade_bench import expand_px
    return expand_px(el)


def refine(spec, img, find=("window",), thr=0.6, snap=False):
    parts = [p for p in spec["parts"] if p.get("type") == "facade"]
    if len(parts) != 1 or "px" not in parts[0]:
        raise ValueError("spec needs exactly one facade part with px")
    f = parts[0]
    region = f["px"]
    gx, gy = gradients(img)
    out, added, snapped = [], 0, 0
    by_class = {}
    for el in f["els"]:
        boxes = expand(el)
        by_class.setdefault(el["k"], []).extend(boxes)
        extra = dict((k, v) for k, v in el.items() if k in ("d", "bars"))
        out.extend(dict(extra, k=el["k"], box=b) for b in boxes)
    for k in find:
        templates = [el for el in f["els"] if el["k"] == k]
        for el in templates:
            matches = find_matches(img, el["box"], region, thr, by_class.get(k, []))
            by_class.setdefault(k, []).extend(matches)
            extra = dict((kk, v) for kk, v in el.items() if kk in ("d", "bars"))
            out.extend(dict(extra, k=k, box=b) for b in matches)
            added += len(matches)
    if snap:
        for el in out:
            if el["k"] in SNAP_CLASSES:
                nb = snap_box(el["box"], gx, gy)
                if nb != [int(round(v)) for v in el["box"]]:
                    snapped += 1
                el["box"] = nb
    f = dict(f, els=out)
    new = dict(spec, parts=[f if p is parts[0] else p for p in spec["parts"]])
    return new, {"added": added, "snapped": snapped, "els": len(out)}


def main(argv):
    if len(argv) < 4:
        raise SystemExit(__doc__)
    image, src, dst = argv[1:4]
    opts = argv[4:]
    find = ("window",)
    thr, snap = 0.6, False
    i = 0
    while i < len(opts):
        if opts[i] == "--find":
            find = tuple(k for k in opts[i + 1].split(",") if k)
            i += 2
        elif opts[i] == "--thr":
            thr = float(opts[i + 1])
            i += 2
        elif opts[i] == "--snap":
            snap = True
            i += 1
        else:
            raise SystemExit("unknown option %r" % opts[i])
    with open(src, encoding="utf-8") as fh:
        spec = json.load(fh)
    new, stats = refine(spec, load_gray(image), find, thr, snap)
    text = json.dumps(new, separators=(",", ":"))   # serialise fully before touching dst
    tmp = dst + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, dst)
    print(json.dumps(stats))


if __name__ == "__main__":
    main(sys.argv)
