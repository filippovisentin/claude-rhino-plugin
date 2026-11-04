"""Clean-up of detector boxes before they become a facade draft.

    dedupe(dets) -> dets        dets: [(class, conf, x0, y0, x1, y1)] in image pixels

Same-class boxes that mostly overlap keep only the most confident one, so a window is not built
twice. Measured on the 22 CMP test facades and 4 hznu photos (all11s, conf 0.25): neutral on
IoU (0.617 -> 0.616, hznu 0.801 -> 0.800) while removing doubled elements from the model.

Tried and rejected: snapping boxes to shared rows and columns with one median size. It looks
tidier but lowered accuracy (CMP 0.617 -> 0.610, hznu openings 0.801 -> 0.732): rows in a photo
are rarely exactly level (residual perspective, lens), and the detector already follows them.
"""


def _area(b):
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _inter(a, b):
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def dedupe(dets, thresh=0.6):
    """Same class, intersection over the smaller box above thresh: keep the confident one."""
    out = []
    for d in sorted(dets, key=lambda d: -d[1]):
        b = d[2:]
        if any(o[0] == d[0] and _inter(b, o[2:]) > thresh * min(_area(b), _area(o[2:])) for o in out):
            continue
        out.append(d)
    return out
