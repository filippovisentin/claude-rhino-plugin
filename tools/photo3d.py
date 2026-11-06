"""From one photo to measured dimensions: the camera from the building's corners, then every outline
read on the photo turned into metres on the plane of its face.

    python tools/photo3d.py solve READING.json OUT.json

READING.json (pixels of the photo, metres, Z up, the building's front along +X at y = 0):

    {"image": [450, 600],
     "known": {"H1": 100},                      # sizes known from the brief or a reference
     "init": {"F": 3.5},                        # optional starting values (small sizes like a floor)
     "limits": {"F": [2.8, 4.5], "Hb": [0, 100]},  # plausible ranges: floors, nothing above the spike
     "points": [                                # corners seen on the photo
        {"px": [93, 377],  "X": [0, 0, "H0"]},   # top-left corner of the front, at the eaves
        {"px": [325, 18],  "X": ["W", 0, "H1"]}, # the spike on the front-right corner
        {"px": [383, 170], "X": ["W", "D", "Hb"]},
        {"px": [73, 573],  "X": [0, 0, "?"]}],   # a point on a vertical edge, height unknown
     "lines": {                                 # outlines to measure, each on its face's plane
        "front roof": {"plane": "y=0", "px": [[93, 377], [140, 360], ...]},
        "side roof":  {"plane": "x=W", "px": [[325, 18], [355, 95], ...]}}}

Coordinates are numbers, names of unknown sizes (solved, shared between points), arithmetic on
sizes ("Zb+3*F": the fourth balcony of a stack with equal floors F; "W+B": a balcony B deep on the
side face x = W), or "?" (a free
value for that point alone: a vertical edge whose foot is hidden). The origin and the axes come
from the zeros; named sizes are positive lengths; at least one size must be known (in "known") to fix the scale. The camera may roll (a handheld
photo is rarely level); its principal point is the image centre; its focal length is searched.

OUT.json: {"rms": pixels, "sizes": {...}, "camera": {"C", "yaw", "pitch", "roll", "f", "image"},
"residuals": [...], "rhino_view": {"location", "target", "lens_35mm", "size"} (the photo's view in
Rhino, metres, for the side-by-side render), "lines": {name: [[a, b], ...]}} where a line's points are (x, z) on a plane
y = k, (y, z) on x = k and (x, y) on z = k, in metres. A residual over 5 px means a point was read
on the wrong corner or a size is not what the reading assumes. "alternatives" lists other sizes
that fit within half a pixel of the best: the corners alone cannot choose between them (a wide
building far away against a deep one near), so add corners, constraints or limits until there are
none, or choose by the building's rules and say so.

The method, for any building: read the corners of every visible face, solve, then build each face's
measured outline (an elevation, a side profile, a plan) as a prism through the building and keep
what they share (a boolean intersection; the spec's `keep` for it is not merged yet); check with
tools/silhouette.py compare --calib OUT.json.
"""
import json
import math
import sys

import numpy as np

FOCALS = (0.6, 0.8, 1.0, 1.3, 1.7, 2.2)   # focal length / long image side tried as starting points


def rotation(yaw, pitch, roll=0.0):
    """Camera axes in the world: x right, y forward, z up; yaw about Z, pitch up, roll about the view."""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    cr, sr = math.cos(roll), math.sin(roll)
    return (np.array([[cy, -sy, 0], [sy, cy, 0], [0, 0, 1]]) @ np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
            @ np.array([[cr, 0, sr], [0, 1, 0], [-sr, 0, cr]]))


def project(cam, pts):
    """Pixels (u, v) of world points (N x 3) seen by cam; points behind the camera get nan."""
    w, h = cam["image"]
    d = (np.asarray(pts, float) - np.asarray(cam["C"], float)) @ rotation(cam["yaw"], cam["pitch"], cam.get("roll", 0.0))
    depth = np.where(d[:, 1] > 1e-6, d[:, 1], np.nan)
    return np.stack([w / 2 + cam["f"] * d[:, 0] / depth, h / 2 - cam["f"] * d[:, 2] / depth], 1)


def ray(cam, u, v):
    w, h = cam["image"]
    return rotation(cam["yaw"], cam["pitch"], cam.get("roll", 0.0)) @ np.array([(u - w / 2) / cam["f"], 1.0, -(v - h / 2) / cam["f"]])


def on_plane(cam, u, v, axis, value):
    d = ray(cam, u, v)
    if abs(d[axis]) < 1e-12:
        return None
    t = (value - cam["C"][axis]) / d[axis]
    return None if t <= 0 else np.asarray(cam["C"], float) + t * d


def _expr(text):
    """A coordinate written as arithmetic on sizes ("Zb+3*F", "W+B"): returns (names, function).
    Only names, numbers, + - * / and brackets: a regular building's rules (equal floors, equal
    bays) become constraints."""
    import ast
    tree = ast.parse(text, mode="eval")
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif not isinstance(node, (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Load,
                                   ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd)):
            raise ValueError("coordinate %r: only sizes, numbers and + - * /" % text)
    code = compile(tree, "<coordinate>", "eval")
    return names, lambda env: float(eval(code, {"__builtins__": {}}, env))


class Reading:
    def __init__(self, data):
        self.image = data["image"]
        self.known = dict(data.get("known", {}))
        self.limits = dict(data.get("limits", {}))
        self.points = data["points"]
        self.names, self.free = [], 0
        self.exprs = {}
        for p in self.points:
            for c in p["X"]:
                if c == "?":
                    self.free += 1
                elif isinstance(c, str):
                    names, fn = _expr(c)
                    self.exprs[c] = fn
                    for n in names:
                        if n not in self.known and n not in self.names:
                            self.names.append(n)
        if not self.known:
            raise ValueError("give at least one known size in \"known\" to fix the scale")

    def coords(self, sizes, free):
        out, k = [], 0
        env = dict(self.known, **sizes)
        for p in self.points:
            row = []
            for c in p["X"]:
                if c == "?":
                    row.append(free[k])
                    k += 1
                elif isinstance(c, str):
                    row.append(self.exprs[c](env))
                else:
                    row.append(float(c))
            out.append(row)
        return np.array(out)

    def unpack(self, q, f):
        n = len(self.names)
        sizes = dict(zip(self.names, q[:n]))
        free = q[n:n + self.free]
        C = q[n + self.free:n + self.free + 3]
        yaw, pitch, roll = q[-3], q[-2], q[-1]
        return sizes, free, {"C": C.tolist(), "yaw": float(yaw), "pitch": float(pitch), "roll": float(roll),
                             "f": f, "image": self.image}

    def residual(self, q, f):
        sizes, free, cam = self.unpack(q, f)
        uv = project(cam, self.coords(sizes, free))
        r = (uv - np.array([p["px"] for p in self.points], float)).ravel()
        # sizes are lengths: a negative one is the mirror solution (a side face coming towards
        # the camera instead of going away), which fits the corners as well
        neg = [1e3 * max(0.0, -v) for v in sizes.values()]
        # plausible ranges from the brief or building rules ("F": [2.8, 4.5] for a floor): a
        # numerically better fit outside them is a different, wrong building
        lim = [1e3 * (max(0.0, lo - sizes[n]) + max(0.0, sizes[n] - hi))
               for n, (lo, hi) in self.limits.items() if n in sizes]
        return np.nan_to_num(np.concatenate([r, neg, lim]), nan=1e4)


def _lm(fun, q, it=500):
    """Levenberg-Marquardt with a numeric Jacobian."""
    q = np.array(q, float)
    r = fun(q)
    e, lam = r @ r, 1e-2
    for _ in range(it):
        J = np.empty((len(r), len(q)))
        for j in range(len(q)):
            h = 1e-6 * max(1.0, abs(q[j]))
            qq = q.copy()
            qq[j] += h
            J[:, j] = (fun(qq) - r) / h
        A, g = J.T @ J, J.T @ r
        try:
            step = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-9), -g)
        except np.linalg.LinAlgError:
            lam *= 10
            continue
        qn = q + step
        rn = fun(qn)
        en = rn @ rn
        if en < e:
            done = e - en < 1e-10 * max(e, 1.0)
            q, r, e, lam = qn, rn, en, lam * 0.3
            if done:
                break
        else:
            lam *= 5
            if lam > 1e9:
                break
    return q, e


def solve(data):
    rd = Reading(data)
    w, h = rd.image
    scale = max(abs(v) for v in rd.known.values())
    best, found = None, []
    for fk in FOCALS:
        f = fk * max(w, h)
        for yaw in np.radians([-60, -30, 0, 30, 60]):
            for dist in (1.5, 3.0):
                for pitch in np.radians([0, 15, 30]):
                    # the camera looks along (-sin yaw, cos yaw): start it that far back from the
                    # building, looking at it
                    C0 = [scale * 0.3 + dist * scale * math.sin(yaw), -dist * scale * math.cos(yaw), scale * 0.1]
                    init = data.get("init", {})
                    q0 = [init.get(n, scale * 0.5) for n in rd.names] + [scale * 0.2] * rd.free + C0 + [yaw, pitch, 0.0]
                    q, e = _lm(lambda q: rd.residual(q, f), q0)
                    # refine the focal length once the rest has settled
                    for f2 in (f * 0.9, f * 1.1):
                        q2, e2 = _lm(lambda q: rd.residual(q, f2), q, it=100)
                        if e2 < e:
                            q, e, f = q2, e2, f2
                    found.append((e, q, f))
                    if best is None or e < best[1]:
                        best = (q, e, f)
    q, e, f = best
    # other buildings that fit the corners almost as well: the reading cannot tell them apart,
    # the building's rules (whole floors from the ground, plausible proportions) or more corners can
    npx = max(1, 2 * len(rd.points))
    rms_of = lambda err: math.sqrt(err / npx)
    alts = []
    for e2, q2, f2 in sorted(found, key=lambda t: t[0]):
        if rms_of(e2) > rms_of(e) + 0.5:
            break
        s2 = rd.unpack(q2, f2)[0]
        if all(any(abs(s2[n] - a[n]) > 0.05 * max(abs(a[n]), 1.0) for n in s2) for a in [x[1] for x in alts]):
            alts.append((round(rms_of(e2), 2), {n: round(float(v), 3) for n, v in s2.items()}))
        if len(alts) == 4:
            break
    sizes, free, cam = rd.unpack(q, f)
    res = rd.residual(q, f)[:2 * len(rd.points)].reshape(-1, 2)
    out = {"rms": round(math.sqrt(e / max(1, res.size)), 2),
           "sizes": {k: round(float(v), 3) for k, v in sizes.items()},
           "camera": cam,
           "residuals": [round(float(np.hypot(*r)), 1) for r in res],
           "alternatives": [{"rms": r, "sizes": s} for r, s in alts[1:]],
           "lines": {}}
    # the same view in Rhino (metres): the side-by-side render of the method
    fw = rotation(cam["yaw"], cam["pitch"], cam.get("roll", 0.0)) @ np.array([0.0, 1.0, 0.0])
    out["rhino_view"] = {"location": [round(float(c), 3) for c in cam["C"]],
                         "target": [round(float(c + 50 * d), 3) for c, d in zip(cam["C"], fw)],
                         "lens_35mm": round(f * 36.0 / max(w, h), 2), "size": [w, h]}
    allsizes = dict(rd.known, **sizes)
    for name, line in data.get("lines", {}).items():
        axis_name, val = line["plane"].replace(" ", "").split("=")
        axis = "xyz".index(axis_name)
        value = allsizes[val] if val in allsizes else float(val)
        keep = [i for i in range(3) if i != axis]
        pts = []
        for u, v in line["px"]:
            P = on_plane(cam, u, v, axis, value)
            if P is not None:
                pts.append([round(float(P[keep[0]]), 3), round(float(P[keep[1]]), 3)])
        out["lines"][name] = pts
    return out


def main(argv):
    if len(argv) != 3 or argv[0] != "solve":
        print(__doc__)
        return 2
    with open(argv[1]) as fh:
        data = json.load(fh)
    out = solve(data)
    with open(argv[2], "w") as fh:
        json.dump(out, fh, indent=1)
    print(json.dumps({"rms": out["rms"], "sizes": out["sizes"], "worst": max(out["residuals"]),
                      "alternatives": out["alternatives"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
