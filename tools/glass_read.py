"""Glass openings of a straightened facade as rectangles in metres, by colour: for curtain walls and
free glazing patterns the facade detector was not trained on (strips, staggered panes).

    data\\venv-det\\Scripts\\python.exe tools/glass_read.py FACADE.jpg W H OUT.json [--floor F] [--outline CALIB.json LINE H0]

FACADE.jpg  the face straightened by tools/rectify.py over the rectangle 0..W x 0..H metres (image
            top = H, bottom = ground)
--floor     floor height F: rectangles start and end on half floors (default 3.3)
--outline   keep only what lies under a measured top line: the line LINE of tools/photo3d.py's
            output CALIB.json, from the eaves H0 at x = 0 up to x = W

How: the facade's own pixels are split into two colour groups (bright low-saturation panels, the
darker or more saturated glass); trees and cars (green, dark grey) and the black area outside the
photo are unknown and take the facade three floors higher (facades repeat); the glass is then sampled
on cells of 0.3 m x half a floor and covered greedily with the largest all-glass rectangles.

Prints {"glass_iou": overlap of the rectangles with the glass pixels, "rects": n}; OUT.json holds
{"floor": F, "rects": [[u, v, w, h], ...]} for `k:"window"` elements of a facade in metres.
"""
import argparse
import json
import sys

import cv2
import numpy as np

CELL_W = 0.3


def read(path, W, H, floor=3.3, top=None):
    img = cv2.imread(path)
    h, w = img.shape[:2]
    k = w / W
    inside = np.ones((h, w), np.uint8)
    if top:
        poly = np.array([[0, h]] + [[x * k, (H - z) * k] for x, z in top] + [[w, h]], np.int32)
        inside = np.zeros((h, w), np.uint8)
        cv2.fillPoly(inside, [poly], 1)
    inside = inside.astype(bool)
    frame = img.max(2) > 0
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(float)
    sat, val = hsv[:, :, 1] / 255, hsv[:, :, 2] / 255
    b, g = img[:, :, 0].astype(int), img[:, :, 1].astype(int)
    hide = ((g > b + 5) | ((val < 0.4) & (sat < 0.35))) & inside
    hide = cv2.morphologyEx(hide.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8)).astype(bool)
    known = inside & frame & ~hide
    X = np.stack([sat[known], val[known]], 1).astype(np.float32)
    _, lab, cent = cv2.kmeans(X, 2, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.01),
                              5, cv2.KMEANS_PP_CENTERS)
    glass_group = int(np.argmax(cent[:, 0] - cent[:, 1]))    # more saturated and darker
    glass = np.zeros((h, w), bool)
    glass[known] = lab.ravel() == glass_group

    ch = floor / 2
    nx, ny = int(np.ceil(W / CELL_W)), int(np.ceil(H / ch))
    cell = np.zeros((ny, nx), np.int8)      # 1 glass, 0 wall, 2 unknown, -1 outside
    for j in range(ny):
        y1, y0 = int(round(h - j * ch * k)), max(0, int(round(h - (j + 1) * ch * k)))
        for i in range(nx):
            x0, x1 = int(round(i * CELL_W * k)), min(w, int(round((i + 1) * CELL_W * k)))
            ins = inside[y0:y1, x0:x1]
            if y1 <= y0 or ins.size == 0 or ins.mean() < 0.5:
                cell[j, i] = -1
                continue
            kn = known[y0:y1, x0:x1]
            if kn.mean() < 0.5:
                cell[j, i] = 2
                continue
            cell[j, i] = 1 if glass[y0:y1, x0:x1][kn].mean() >= 0.6 else 0
    for j in range(ny):                     # hidden: the facade three floors higher
        for i in range(nx):
            if cell[j, i] == 2:
                t = j + 6
                while t < ny and cell[t, i] == 2:
                    t += 6
                cell[j, i] = cell[t, i] if t < ny and cell[t, i] in (0, 1) else 0

    left, rects = cell == 1, []
    while left.sum() > 3:
        area, rc = _largest(left)
        if area < 4:
            break
        j0, j1, i0, i1 = rc
        left[j0:j1 + 1, i0:i1 + 1] = False
        rects.append([round(i0 * CELL_W, 3), round(j0 * ch, 3), round((i1 - i0 + 1) * CELL_W, 3), round((j1 - j0 + 1) * ch, 3)])
    rec = np.zeros((h, w), bool)
    for u, v, ww, hh in rects:
        rec[max(0, int(h - (v + hh) * k)):int(h - v * k), int(u * k):int((u + ww) * k)] = True
    iou = (rec & glass & known).sum() / max(((rec | glass) & known).sum(), 1)
    return rects, float(iou)


def _largest(m):
    """Largest all-True rectangle of a boolean matrix (histogram method): (area, (j0, j1, i0, i1))."""
    best, hgt = (0, None), np.zeros(m.shape[1], int)
    for j in range(m.shape[0]):
        hgt = np.where(m[j], hgt + 1, 0)
        stack = []
        for i in range(m.shape[1] + 1):
            cur = hgt[i] if i < m.shape[1] else 0
            start = i
            while stack and stack[-1][1] >= cur:
                s0, hh = stack.pop()
                if hh * (i - s0) > best[0]:
                    best = (hh * (i - s0), (j - hh + 1, j, s0, i - 1))
                start = s0
            stack.append((start, cur))
    return best


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image")
    ap.add_argument("W", type=float)
    ap.add_argument("H", type=float)
    ap.add_argument("out")
    ap.add_argument("--floor", type=float, default=3.3)
    ap.add_argument("--outline", nargs=3, metavar=("CALIB", "LINE", "H0"))
    a = ap.parse_args(argv)
    top = None
    if a.outline:
        with open(a.outline[0]) as fh:
            line = [list(p) for p in json.load(fh)["lines"][a.outline[1]]]
        line[0] = [0.0, float(a.outline[2])]
        line[-1] = [a.W, line[-1][1]]
        top = line
    rects, iou = read(a.image, a.W, a.H, a.floor, top)
    with open(a.out, "w") as fh:
        json.dump({"floor": a.floor, "rects": rects}, fh)
    print(json.dumps({"glass_iou": round(iou, 3), "rects": len(rects)}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
