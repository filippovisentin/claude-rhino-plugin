# -*- coding: utf-8 -*-
"""Validation and normalisation of a rhinospec model description.

A spec is plain JSON that Claude writes instead of RhinoCommon code. It is cheaper in tokens,
it cannot run arbitrary code, and the same spec always produces the same geometry.

Pure Python, compatible with CPython 3 and IronPython 2.7, so it is tested outside Rhino.
"""
from __future__ import division

import math
import re

VERSION = 1
UNITS = ("mm", "cm", "m")
MAX_PARTS = 2000         # after arrays, buildings and facades are expanded
MAX_POINTS = 500         # per polyline / profile
MAX_COORD = 1.0e6        # absolute coordinate or size, in spec units
MAX_FLOORS = 100
MAX_CUTS = 50
MAX_HOLES = 500
MAX_ELEMENTS = 1000     # facade elements after grids are expanded
# \Z, not $: "$" also matches before a trailing newline.
NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]{1,64}\Z")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}\Z")

PRIMITIVES = ("box", "cyl", "cone", "sphere", "torus", "extrude", "prism", "revolve", "loft", "pipe", "panel")
COMPOSITES = ("array", "building", "facade", "block", "stair", "column")
# Classical orders: column height in lower diameters (Vignola).
ORDERS = {"tuscan": 7.0, "doric": 8.0, "ionic": 9.0, "corinthian": 10.0}
FACADE_CLASSES = ("window", "door", "shop", "balcony", "cornice", "molding", "pillar", "sill", "blind", "deco", "rustic", "quoin", "spandrel", "pediment", "arcade", "clad", "pipe", "finial")
DECO_SHAPES = ("block", "console", "oval", "panel")
FINIAL_SHAPES = ("urn", "ball", "spire")
STYLES = ("plain", "classic", "modern")
RAILS = ("balustrade", "iron", "solid", "glass")
LEAVES = ("panel", "glass", "garage")   # door leaf: panelled, glazed (French, patio), sectional
OPENINGS = ("window", "door", "shop")
COMMON_KEYS = ("type", "name", "at", "rot", "tilt", "color", "cut", "group", "obj", "cat", "join")

_KEYS = {
    "box": ("size",),
    "cyl": ("r", "h"),
    "cone": ("r", "h", "r2"),
    "sphere": ("r",),
    "torus": ("R", "r"),
    "extrude": ("pts", "h"),
    "prism": ("pts", "len"),
    "revolve": ("profile",),
    "loft": ("sections",),
    "pipe": ("path", "r"),
    "panel": ("size", "t", "holes"),
    "array": ("of", "n", "step"),
    "building": ("footprint", "floors", "floor_h", "wall_t", "slab_t", "openings", "roof", "roof_h"),
    "facade": ("w", "h", "t", "els", "frac", "px", "depth", "floors", "roof", "roof_h", "style", "dormers", "chimneys", "palette", "top"),
    "column": ("order", "h", "d", "count", "spacing", "axis"),
    "stair": ("kind", "h", "w", "r", "core", "tread", "step", "rail"),
    "block": ("w", "d", "h", "t", "floors", "roof", "roof_h", "faces", "style", "dormers", "chimneys", "palette"),
}

FACES = ("front", "right", "back", "left")


class SpecError(ValueError):
    """Raised with a short, path-qualified message Claude can act on."""


def _fail(path, msg):
    raise SpecError("%s: %s" % (path, msg))


def _num(v, path, lo=-MAX_COORD, hi=MAX_COORD, positive=False):
    # bool is an int subclass; reject it explicitly.
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        _fail(path, "expected a number")
    v = float(v)
    if math.isnan(v) or math.isinf(v):
        _fail(path, "must be finite")
    if positive and v <= 0:
        _fail(path, "must be > 0")
    if v < lo or v > hi:
        _fail(path, "out of range [%g, %g]" % (lo, hi))
    return v


def _int(v, path, lo, hi):
    if isinstance(v, bool) or not isinstance(v, int):
        _fail(path, "expected an integer")
    if v < lo or v > hi:
        _fail(path, "out of range [%d, %d]" % (lo, hi))
    return v


def _vec(v, path, n, positive=False):
    if not isinstance(v, list) or len(v) != n:
        _fail(path, "expected %d numbers" % n)
    return [_num(x, "%s[%d]" % (path, i), positive=positive) for i, x in enumerate(v)]


def _pts(v, path, dim, min_n):
    if not isinstance(v, list) or not (min_n <= len(v) <= MAX_POINTS):
        _fail(path, "expected %d..%d points" % (min_n, MAX_POINTS))
    return [_vec(p, "%s[%d]" % (path, i), dim) for i, p in enumerate(v)]


def polygon_area(pts):
    """Signed area of a 2D polygon: positive when counter-clockwise."""
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i][0], pts[i][1]
        x1, y1 = pts[(i + 1) % len(pts)][0], pts[(i + 1) % len(pts)][1]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _polygon(v, path):
    pts = _pts(v, path, 2, 3)
    if len(pts) > 3 and pts[0] == pts[-1]:
        pts = pts[:-1]  # tolerate an explicitly closed polygon
    if abs(polygon_area(pts)) < 1e-9:
        _fail(path, "polygon has zero area")
    return pts


def _unknown(part, allowed, path):
    extra = sorted(k for k in part if k not in allowed)
    if extra:
        _fail(path, "unknown key(s) %s" % ", ".join(extra))


def _common(part, path, allow_cut=True):
    out = {"type": part["type"]}
    if "name" in part:
        if not isinstance(part["name"], str) or not NAME_RE.match(part["name"]):
            _fail(path + ".name", "1-64 chars of letters, digits, space, _ . -")
        out["name"] = part["name"]
    out["at"] = _vec(part.get("at", [0, 0, 0]), path + ".at", 3)
    out["rot"] = _num(part.get("rot", 0), path + ".rot", -360, 360)
    if "tilt" in part:   # [about x, about y] degrees, applied before rot
        tilt = part["tilt"]
        if not isinstance(tilt, list) or len(tilt) != 2:
            _fail(path + ".tilt", "expected [degrees about x, degrees about y]")
        out["tilt"] = [_num(tilt[0], path + ".tilt[0]", -360, 360), _num(tilt[1], path + ".tilt[1]", -360, 360)]
    for key in ("group", "obj", "join"):   # sublayers; join: parts sharing it (and a layer) become one solid
        if key in part:
            if not isinstance(part[key], str) or not NAME_RE.match(part[key]):
                _fail("%s.%s" % (path, key), "1-64 chars of letters, digits, space, _ . -")
            out[key] = part[key]
    if "cat" in part:              # a standard category layer, e.g. "windows/glass"
        from .naming import CATEGORIES
        if part["cat"] not in CATEGORIES:
            _fail(path + ".cat", "unknown category; one of %s" % ", ".join(sorted(CATEGORIES)))
        out["cat"] = part["cat"]
    if "color" in part:
        if not isinstance(part["color"], str) or not COLOR_RE.match(part["color"]):
            _fail(path + ".color", "expected #rrggbb")
        out["color"] = part["color"].lower()
    if "cut" in part:
        if not allow_cut:
            _fail(path + ".cut", "cutters cannot have their own cuts")
        cuts = part["cut"]
        if not isinstance(cuts, list) or not (1 <= len(cuts) <= MAX_CUTS):
            _fail(path + ".cut", "expected 1..%d parts" % MAX_CUTS)
        out["cut"] = [_primitive(c, "%s.cut[%d]" % (path, i), allow_cut=False) for i, c in enumerate(cuts)]
    return out


def _primitive(part, path, allow_cut=True):
    if not isinstance(part, dict):
        _fail(path, "expected an object")
    t = part.get("type")
    if t not in PRIMITIVES:
        _fail(path + ".type", "expected one of %s" % ", ".join(PRIMITIVES))
    _unknown(part, COMMON_KEYS + _KEYS[t], path)
    out = _common(part, path, allow_cut)
    g = part.get
    if t == "box":
        out["size"] = _vec(g("size"), path + ".size", 3, positive=True)
    elif t in ("cyl", "cone"):
        out["r"] = _num(g("r"), path + ".r", positive=True)
        out["h"] = _num(g("h"), path + ".h", positive=True)
        if t == "cone":
            out["r2"] = _num(g("r2", 0), path + ".r2", lo=0)
    elif t == "sphere":
        out["r"] = _num(g("r"), path + ".r", positive=True)
    elif t == "torus":
        out["R"] = _num(g("R"), path + ".R", positive=True)
        out["r"] = _num(g("r"), path + ".r", positive=True)
        if out["r"] >= out["R"]:
            _fail(path + ".r", "must be smaller than R")
    elif t == "extrude":
        out["pts"] = _polygon(g("pts"), path + ".pts")
        out["h"] = _num(g("h"), path + ".h", positive=True)
    elif t == "prism":
        out["pts"] = _polygon(g("pts"), path + ".pts")  # profile in the local XZ plane
        out["len"] = _num(g("len"), path + ".len", positive=True)
    elif t == "revolve":
        prof = _pts(g("profile"), path + ".profile", 2, 2)
        for i, p in enumerate(prof):
            if p[0] < 0:
                _fail("%s.profile[%d][0]" % (path, i), "radius must be >= 0")
        out["profile"] = prof
    elif t == "loft":
        secs = g("sections")
        if not isinstance(secs, list) or not (2 <= len(secs) <= 50):
            _fail(path + ".sections", "expected 2..50 sections")
        out["sections"] = []
        last_z = None
        for i, s in enumerate(secs):
            sp = "%s.sections[%d]" % (path, i)
            if not isinstance(s, dict):
                _fail(sp, "expected {pts, z}")
            _unknown(s, ("pts", "z"), sp)
            z = _num(s.get("z"), sp + ".z")
            if last_z is not None and z <= last_z:
                _fail(sp + ".z", "sections must rise strictly in z")
            last_z = z
            pts = _polygon(s.get("pts"), sp + ".pts")
            if out["sections"] and len(pts) != len(out["sections"][0]["pts"]):
                _fail(sp + ".pts", "every section needs the same number of points")
            out["sections"].append({"pts": pts, "z": z})
    elif t == "pipe":
        out["path"] = _pts(g("path"), path + ".path", 3, 2)
        out["r"] = _num(g("r"), path + ".r", positive=True)
    elif t == "panel":
        out["size"] = _vec(g("size"), path + ".size", 2, positive=True)  # [width u, height v] in local XZ
        out["t"] = _num(g("t"), path + ".t", positive=True)               # thickness along local +y
        holes = g("holes", [])
        if not isinstance(holes, list) or len(holes) > MAX_HOLES:
            _fail(path + ".holes", "expected at most %d holes" % MAX_HOLES)
        out["holes"] = []
        for i, h in enumerate(holes):
            hp = "%s.holes[%d]" % (path, i)
            if isinstance(h, list) and len(h) == 5:
                hole = _vec(h[:4], hp, 4) + [_int(h[4], hp + "[4]", 0, 3)]   # 0 rect, 1 arch, 2 seg, 3 round
            else:
                hole = _vec(h, hp, 4)
            out["holes"].append(hole)
        check_holes(out["size"], out["holes"], path + ".holes")
    return out


def check_holes(size, holes, path):
    """Holes are [u, v, w, h] rectangles strictly inside the panel and not overlapping."""
    w, h = size
    for i, (u, v, hw, hh) in enumerate(hh[:4] for hh in holes):
        if hw <= 0 or hh <= 0:
            _fail("%s[%d]" % (path, i), "width and height must be > 0")
        if u <= 0 or v <= 0 or u + hw >= w or v + hh >= h:
            _fail("%s[%d]" % (path, i), "must lie strictly inside the panel")
    for i in range(len(holes)):
        for j in range(i + 1, len(holes)):
            if rects_overlap(holes[i], holes[j], HOLE_GAP):
                _fail("%s[%d]" % (path, j), "overlaps or touches hole %d" % i)


def rects_overlap(a, b, gap=0.0):
    """True when two [u, v, w, h] rectangles overlap or come closer than gap."""
    return (a[0] < b[0] + b[2] + gap and b[0] < a[0] + a[2] + gap and
            a[1] < b[1] + b[3] + gap and b[1] < a[1] + a[3] + gap)


HOLE_GAP = 1e-3   # hole loops that touch share an edge, and Rhino can't build that face


def _array(part, path):
    _unknown(part, ("type", "name", "of", "n", "step", "group", "turn", "pivot"), path)
    turn = _num(part.get("turn", 0), path + ".turn", -360, 360)   # degrees per copy, about Z
    pivot = _vec(part.get("pivot", [0, 0]), path + ".pivot", 2)
    of = part.get("of")
    n = part.get("n")
    if not isinstance(n, list) or len(n) != 3:
        _fail(path + ".n", "expected [nx, ny, nz]")
    n = [_int(x, "%s.n[%d]" % (path, i), 1, MAX_PARTS) for i, x in enumerate(n)]
    total = n[0] * n[1] * n[2]
    if total > MAX_PARTS:
        _fail(path + ".n", "%d copies exceed the %d part limit" % (total, MAX_PARTS))
    step = _vec(part.get("step"), path + ".step", 3)
    base = _primitive(of, path + ".of")
    out = []
    idx = 0
    for k in range(n[2]):
        for j in range(n[1]):
            for i in range(n[0]):
                c = dict(base)
                x, y = base["at"][0] + i * step[0], base["at"][1] + j * step[1]
                if turn:
                    # Copy idx turns by idx * turn about the vertical axis through pivot (spirals,
                    # radial patterns); its own rot turns with it.
                    a = math.radians(turn * idx)
                    dx, dy = x - pivot[0], y - pivot[1]
                    x, y = pivot[0] + dx * math.cos(a) - dy * math.sin(a), pivot[1] + dx * math.sin(a) + dy * math.cos(a)
                    r = base["rot"] + turn * idx
                    c["rot"] = ((r + 360.0) % 720.0) - 360.0
                c["at"] = [x, y, base["at"][2] + k * step[2]]
                idx += 1
                if "name" in part and "name" not in base:
                    c["name"] = part["name"]
                if "group" in part and "group" not in base:
                    if not isinstance(part["group"], str) or not NAME_RE.match(part["group"]):
                        _fail(path + ".group", "1-64 chars of letters, digits, space, _ . -")
                    c["group"] = part["group"]
                out.append(c)
    return out


PER_M = {"mm": 1000.0, "cm": 100.0, "m": 1.0}


def _building(part, path, m=1.0):
    _unknown(part, ("type", "name", "at", "color") + _KEYS["building"], path)
    b = {
        "footprint": _polygon(part.get("footprint"), path + ".footprint"),
        "floors": _int(part.get("floors", 1), path + ".floors", 1, MAX_FLOORS),
        "floor_h": _num(part.get("floor_h", 3.0 * m), path + ".floor_h", positive=True),
        "wall_t": _num(part.get("wall_t", 0.3 * m), path + ".wall_t", positive=True),
        "slab_t": _num(part.get("slab_t", 0.3 * m), path + ".slab_t", positive=True),
        "roof": part.get("roof", "flat"),
        "roof_h": _num(part.get("roof_h", 2.0 * m), path + ".roof_h", positive=True),
        "at": _vec(part.get("at", [0, 0, 0]), path + ".at", 3),
        "openings": [],
    }
    if b["roof"] not in ("flat", "gable", "none"):
        _fail(path + ".roof", "expected flat, gable or none")
    if b["slab_t"] >= b["floor_h"]:
        _fail(path + ".slab_t", "must be smaller than floor_h")
    if "name" in part:
        if not isinstance(part["name"], str) or not NAME_RE.match(part["name"]):
            _fail(path + ".name", "1-64 chars of letters, digits, space, _ . -")
        b["name"] = part["name"]
    if "color" in part:
        if not isinstance(part["color"], str) or not COLOR_RE.match(part["color"]):
            _fail(path + ".color", "expected #rrggbb")
        b["color"] = part["color"].lower()
    ops = part.get("openings", [])
    if not isinstance(ops, list) or len(ops) > MAX_PARTS:
        _fail(path + ".openings", "expected a list")
    nwalls = len(b["footprint"])
    for i, o in enumerate(ops):
        op = "%s.openings[%d]" % (path, i)
        if not isinstance(o, dict):
            _fail(op, "expected an object")
        _unknown(o, ("wall", "offset", "width", "height", "sill", "floor", "count", "gap"), op)
        floor = o.get("floor", "all")
        if floor != "all":
            floor = _int(floor, op + ".floor", 0, b["floors"] - 1)
        b["openings"].append({
            "wall": _int(o.get("wall"), op + ".wall", 0, nwalls - 1),
            "offset": _num(o.get("offset", 0.5 * m), op + ".offset", lo=0),
            "width": _num(o.get("width", 1.2 * m), op + ".width", positive=True),
            "height": _num(o.get("height", 1.4 * m), op + ".height", positive=True),
            "sill": _num(o.get("sill", 0.9 * m), op + ".sill", lo=0),
            "floor": floor,
            "count": _int(o.get("count", 1), op + ".count", 1, 100),
            "gap": _num(o.get("gap", 1.0 * m), op + ".gap", lo=0),
        })
    return b


def _facade(part, path, m=1.0):
    _unknown(part, ("type", "name", "at", "rot", "color") + _KEYS["facade"], path)
    px = None
    if "px" in part:
        # Element boxes are [x0, y0, x1, y1] pixel corners of a rectified photo, y down; the
        # facade itself spans px. Width defaults to the photo's proportions.
        px = _vec(part["px"], path + ".px", 4)
        if px[2] - px[0] < 1 or px[3] - px[1] < 1:
            _fail(path + ".px", "expected [x0, y0, x1, y1] with x1 > x0 and y1 > y0")
        if part.get("frac"):
            _fail(path + ".frac", "use either px or frac")
    h = _num(part.get("h"), path + ".h", positive=True)
    if px is not None and "w" not in part:
        w = h * (px[2] - px[0]) / (px[3] - px[1])
    else:
        w = _num(part.get("w"), path + ".w", positive=True)
    f = {
        "w": w,
        "h": h,
        "t": _num(part.get("t", 0.4 * m), path + ".t", positive=True),
        "per_m": m,
        "at": _vec(part.get("at", [0, 0, 0]), path + ".at", 3),
        "rot": _num(part.get("rot", 0), path + ".rot", -360, 360),
        "els": [],
    }
    for key in ("name", "color"):
        if key in part:
            rx = NAME_RE if key == "name" else COLOR_RE
            if not isinstance(part[key], str) or not rx.match(part[key]):
                _fail("%s.%s" % (path, key), "invalid %s" % key)
            f[key] = part[key].lower() if key == "color" else part[key]
    f["depth"] = _num(part.get("depth", 0), path + ".depth", 0, 1000 * m)
    if "palette" in part:
        f["palette"] = _palette(part["palette"], path + ".palette")
    if f["t"] < 0.05 * m:
        _fail(path + ".t", "walls thinner than 0.05 leave no room for window recesses")
    if f["depth"] and f["depth"] <= 2 * f["t"]:
        _fail(path + ".depth", "must exceed twice the wall thickness t")
    if f["depth"] and f["w"] <= 2 * f["t"]:
        _fail(path + ".w", "with depth, the facade must be wider than two walls")
    f["floors"] = _int(part.get("floors", 1), path + ".floors", 1, MAX_FLOORS)
    f["roof"] = part.get("roof", "flat")
    if f["roof"] not in ("flat", "gable", "hip", "mansard", "none"):
        _fail(path + ".roof", "expected flat, gable, hip, mansard or none")
    f["roof_h"] = _num(part.get("roof_h", 3.0 * m), path + ".roof_h", positive=True)
    f["dormers"] = _int(part.get("dormers", 0), path + ".dormers", 0, 40)

    f["style"] = part.get("style", "plain")
    if f["style"] not in STYLES:
        _fail(path + ".style", "expected plain, classic or modern")
    frac = part.get("frac", False)
    if not isinstance(frac, bool):
        _fail(path + ".frac", "expected true or false")
    # chimneys: a count, or x positions in the units of the boxes (photo pixels with px)
    ch = part.get("chimneys", 0)
    if isinstance(ch, list):
        if not 1 <= len(ch) <= 20:
            _fail(path + ".chimneys", "expected 1..20 positions")
        xs = [_num(x, "%s.chimneys[%d]" % (path, i)) for i, x in enumerate(ch)]
        conv = ((lambda x: (x - px[0]) * f["w"] / (px[2] - px[0])) if px is not None
                else (lambda x: x * f["w"]) if frac else (lambda x: x))
        f["chimney_at"] = [conv(x) for x in xs]
        f["chimneys"] = len(xs)
    else:
        f["chimneys"] = _int(ch, path + ".chimneys", 0, 20)
    els = part.get("els")
    if not isinstance(els, list) or not els:
        _fail(path + ".els", "expected a non-empty list of elements")
    total = 0
    for i, e in enumerate(els):
        ep = "%s.els[%d]" % (path, i)
        if not isinstance(e, dict):
            _fail(ep, "expected an object")
        _unknown(e, ("k", "box", "grid", "xs", "ys", "d", "bars", "shape", "sur", "rail", "leaf", "color"), ep)
        if e.get("k") not in FACADE_CLASSES:
            _fail(ep + ".k", "expected one of %s" % ", ".join(FACADE_CLASSES))
        el = {"k": e["k"], "box": _vec(e.get("box"), ep + ".box", 4)}
        if px is None and (el["box"][2] <= 0 or el["box"][3] <= 0):
            _fail(ep + ".box", "width and height must be > 0")
        grid = e.get("grid", [1, 1, 0, 0])
        if not isinstance(grid, list) or len(grid) != 4:
            _fail(ep + ".grid", "expected [nx, ny, du, dv]")
        el["grid"] = [_int(grid[0], ep + ".grid[0]", 1, MAX_ELEMENTS), _int(grid[1], ep + ".grid[1]", 1, MAX_ELEMENTS),
                      _num(grid[2], ep + ".grid[2]"), _num(grid[3], ep + ".grid[3]")]
        # xs / ys: explicit start positions of every column / row (same units as box), for
        # rhythms a single step can't follow (tall facades drift by pixels per floor).
        offs = None
        if "xs" in e or "ys" in e:
            if "grid" in e:
                _fail(ep + ".xs", "use either grid or xs/ys")
            lists = []
            for key, start in (("xs", el["box"][0]), ("ys", el["box"][1])):
                vals = e.get(key, [start])
                if not isinstance(vals, list) or not (1 <= len(vals) <= MAX_ELEMENTS):
                    _fail("%s.%s" % (ep, key), "expected a list of 1..%d positions" % MAX_ELEMENTS)
                lists.append([_num(x, "%s.%s[%d]" % (ep, key, i)) - start for i, x in enumerate(vals)])
            offs = [[dx, dy] for dy in lists[1] for dx in lists[0]]
        W, H = f["w"], f["h"]
        if px is not None:
            x0, y0, x1, y1 = el["box"]
            if x1 <= x0 or y1 <= y0:
                _fail(ep + ".box", "with px, boxes are [x0, y0, x1, y1] corners")
            sx, sy = W / (px[2] - px[0]), H / (px[3] - px[1])
            el["box"] = [(x0 - px[0]) * sx, (px[3] - y1) * sy, (x1 - x0) * sx, (y1 - y0) * sy]
            el["grid"][2] *= sx
            el["grid"][3] *= -sy   # pixel rows grow downward, v grows upward
            if offs is not None:
                offs = [[dx * sx, -dy * sy] for dx, dy in offs]
        elif frac:  # box and grid steps given as fractions of the facade width and height
            el["box"] = [el["box"][0] * W, el["box"][1] * H, el["box"][2] * W, el["box"][3] * H]
            el["grid"][2] *= W
            el["grid"][3] *= H
            if offs is not None:
                offs = [[dx * W, dy * H] for dx, dy in offs]
        if offs is not None:
            el["offs"] = offs
        total += len(offs) if offs is not None else el["grid"][0] * el["grid"][1]
        if total > MAX_ELEMENTS:
            _fail(ep + ".grid", "facade exceeds %d elements" % MAX_ELEMENTS)
        if "d" in e:
            el["d"] = _num(e["d"], ep + ".d", 0, 10 * m)
        if "shape" in e:
            allowed = (("rect", "arch", "seg", "round") if el["k"] == "window" else ("rect", "arch", "seg") if el["k"] in OPENINGS + ("arcade",) else ("flat", "tri", "seg") if el["k"] == "cornice"
                       else DECO_SHAPES if el["k"] == "deco" else FINIAL_SHAPES if el["k"] == "finial" else ("square", "round") if el["k"] == "pillar" else ())
            if e["shape"] not in allowed:
                _fail(ep + ".shape", "expected one of %s" % (", ".join(allowed) or "nothing for %s" % el["k"]))
            el["shape"] = e["shape"]
        if "sur" in e:
            if el["k"] not in OPENINGS:
                _fail(ep + ".sur", "only windows, doors and shops have a surround")
            el["sur"] = _num(e["sur"], ep + ".sur", 0, 2 * m)
        if "rail" in e:
            if el["k"] != "balcony" or e["rail"] not in RAILS:
                _fail(ep + ".rail", "balconies only: one of %s" % ", ".join(RAILS))
            el["rail"] = e["rail"]
        if "leaf" in e:
            if el["k"] != "door" or e["leaf"] not in LEAVES:
                _fail(ep + ".leaf", "doors only: one of %s" % ", ".join(LEAVES))
            el["leaf"] = e["leaf"]
        if "color" in e:   # this element's own colour (a stone plinth, a dark shop front, a yellow door)
            if not isinstance(e["color"], str) or not COLOR_RE.match(e["color"]):
                _fail(ep + ".color", "expected #rrggbb")
            el["color"] = e["color"].lower()
        if "bars" in e:
            if el["k"] not in OPENINGS:
                _fail(ep + ".bars", "only windows, doors and shops have glazing bars")
            bars = e["bars"]
            if not isinstance(bars, list) or len(bars) != 2:
                _fail(ep + ".bars", "expected [vertical, horizontal]")
            el["bars"] = [_int(bars[0], ep + ".bars[0]", 0, 20), _int(bars[1], ep + ".bars[1]", 0, 20)]
        f["els"].append(el)
    if (f["roof"] in ("hip", "mansard") or f["dormers"] or f["chimneys"]) and not f["depth"]:
        _fail(path + ".depth", "a hip or mansard roof, dormers and chimneys need the building's depth")
    if "top" in part:
        f["top"] = _top(part["top"], path + ".top", f, px, frac)
    return f


def _top(pts, path, f, px, frac):
    """The wall's outline above the eaves, left to right: a gable, a stepped or shaped gable, a
    parapet raised in the middle. Points [x, y] in the units of the boxes; the outline runs from
    the left eaves corner through them to the right one."""
    if f["roof"] in ("hip", "mansard") or f["dormers"] or f["chimneys"]:
        _fail(path, "an outline above the eaves can't be combined with a hip or mansard roof, dormers or chimneys")
    if not isinstance(pts, list) or not 1 <= len(pts) <= 64:
        _fail(path, "expected 1..64 points [x, y]")
    W, H = f["w"], f["h"]
    out = []
    for i, q in enumerate(pts):
        x, y = _vec(q, "%s[%d]" % (path, i), 2)
        if px is not None:
            u, v = (x - px[0]) * W / (px[2] - px[0]), (px[3] - y) * H / (px[3] - px[1])
        elif frac:
            u, v = x * W, y * H
        else:
            u, v = x, y
        tol = 1e-6 * max(W, H)
        if u < -tol or u > W + tol:
            _fail("%s[%d]" % (path, i), "x outside the facade")
        if v < H - tol or v > 4 * H:
            _fail("%s[%d]" % (path, i), "y must be at or above the eaves (h), and below 4 h")
        if out and u < out[-1][0] - tol:
            _fail("%s[%d]" % (path, i), "points go left to right (x never decreasing)")
        u, v = min(max(u, 0.0), W), max(v, H)
        if not out or abs(u - out[-1][0]) > tol or abs(v - out[-1][1]) > tol:
            out.append([u, v])
    if max(v for u, v in out) <= H + 1e-6 * H:
        _fail(path, "the outline never rises above the eaves")
    return out


def _block(part, path, m=1.0):
    """A rectangular volume w (along x) by d (along y) by h with a facade on each side. Every
    face takes the facade element keys (els, px, frac); its width and height come from the
    block, so each face can be read from its own photo."""
    _unknown(part, ("type", "name", "at", "rot", "color") + _KEYS["block"], path)
    b = {
        "w": _num(part.get("w"), path + ".w", positive=True),
        "d": _num(part.get("d"), path + ".d", positive=True),
        "h": _num(part.get("h"), path + ".h", positive=True),
        "t": _num(part.get("t", 0.4 * m), path + ".t", positive=True),
        "per_m": m,
        "at": _vec(part.get("at", [0, 0, 0]), path + ".at", 3),
        "rot": _num(part.get("rot", 0), path + ".rot", -360, 360),
        "floors": _int(part.get("floors", 1), path + ".floors", 1, MAX_FLOORS),
        "roof": part.get("roof", "flat"),
        "roof_h": _num(part.get("roof_h", 3.0 * m), path + ".roof_h", positive=True),
        "dormers": _int(part.get("dormers", 0), path + ".dormers", 0, 40),
        "chimneys": 0,
        "faces": {},
    }
    for key in ("name", "color"):
        if key in part:
            rx = NAME_RE if key == "name" else COLOR_RE
            if not isinstance(part[key], str) or not rx.match(part[key]):
                _fail("%s.%s" % (path, key), "invalid %s" % key)
            b[key] = part[key].lower() if key == "color" else part[key]
    if b["roof"] not in ("flat", "gable", "hip", "mansard", "none"):
        _fail(path + ".roof", "expected flat, gable, hip, mansard or none")
    if "palette" in part:
        b["palette"] = _palette(part["palette"], path + ".palette")
    b["style"] = part.get("style", "plain")
    if b["style"] not in STYLES:
        _fail(path + ".style", "expected plain, classic or modern")
    if b["t"] < 0.05 * m:
        _fail(path + ".t", "walls thinner than 0.05 leave no room for window recesses")
    if b["w"] <= 2 * b["t"] or b["d"] <= 2 * b["t"]:
        _fail(path + ".w", "w and d must exceed twice the wall thickness t")
    faces = part.get("faces", {})
    if not isinstance(faces, dict):
        _fail(path + ".faces", "expected an object with front, right, back, left")
    for key in faces:
        if key not in FACES:
            _fail("%s.faces.%s" % (path, key), "expected one of %s" % ", ".join(FACES))
    for key in FACES:
        if key not in faces:
            continue
        fp = "%s.faces.%s" % (path, key)
        face = faces[key]
        if not isinstance(face, dict):
            _fail(fp, "expected an object")
        _unknown(face, ("els", "px", "frac"), fp)
        sub = dict(face)
        sub.update({"w": b["w"] if key in ("front", "back") else b["d"], "h": b["h"], "t": b["t"],
                    "style": b["style"]})
        b["faces"][key] = _facade(sub, fp, m)["els"]
    ch = part.get("chimneys", 0)
    if isinstance(ch, list):   # x positions in metres along the front
        if not 1 <= len(ch) <= 20:
            _fail(path + ".chimneys", "expected 1..20 positions")
        b["chimney_at"] = [_num(x, "%s.chimneys[%d]" % (path, i), 0, b["w"]) for i, x in enumerate(ch)]
        b["chimneys"] = len(ch)
    else:
        b["chimneys"] = _int(ch, path + ".chimneys", 0, 20)
    if "front" in b["faces"]:
        b["faces"]["front"] = _take_dormers(b, b["faces"]["front"], b["h"])
    return b


PALETTE_KEYS = ("wall", "trim", "frames", "glass", "shutters", "doors", "railings", "roof", "spandrels", "clad")


def _palette(pal, path):
    """Colours read off the photo, by family: {"wall": "#rrggbb", "shutters": ..., ...}."""
    if not isinstance(pal, dict):
        _fail(path, "expected an object of colours")
    out = {}
    for k, v in pal.items():
        if k not in PALETTE_KEYS:
            _fail("%s.%s" % (path, k), "expected one of %s" % ", ".join(PALETTE_KEYS))
        if not isinstance(v, str) or not COLOR_RE.match(v):
            _fail("%s.%s" % (path, k), "expected #rrggbb")
        out[k] = v.lower()
    return out


def _dormer_windows(f):
    """Windows read wholly above the eaves and outside any pediment: dormers on the roof (none
    when the wall itself rises above the eaves: they are windows in that gable)."""
    if f.get("top"):
        return []
    from .plan import _expanded, in_pediment, pediment_boxes
    peds = pediment_boxes(f)
    return [(u, w) for el, u, v, w, h in _expanded(f)
            if el["k"] == "window" and v >= f["h"] - 1e-6 and not in_pediment([u, v, w, h], peds)]


def _take_dormers(b, els, h):
    """On a pitched roof, windows read above the eaves of the front become dormers where they
    are (b["dormer_at"]); they and their shutters and hoods up there leave the face."""
    if b["roof"] not in ("gable", "hip", "mansard"):
        return els
    spots = _dormer_windows({"els": els, "h": h})
    if not spots:
        return els
    from .plan import in_pediment, pediment_boxes
    peds = pediment_boxes({"els": els, "h": h})
    b["dormer_at"] = spots
    return [el for el in els if not (el["box"][1] >= h - 1e-6 and el["k"] not in ("pediment", "finial")
                                     and not in_pediment(el["box"], peds))]


def _needs_block(f):
    roofed = f["roof"] in ("gable", "hip", "mansard")
    return bool(f["depth"]) and (f["roof"] in ("hip", "mansard") or f["dormers"] > 0 or f["chimneys"] > 0
                                 or (roofed and bool(_dormer_windows(f))))


def _as_block(f):
    """A facade with depth and a hip/mansard roof, dormers or chimneys: the block of that depth
    with this facade as its front, so the roof, dormers and chimneys come from plan_block."""
    b = dict((k, f[k]) for k in ("w", "h", "t", "per_m", "at", "rot", "floors", "roof", "roof_h",
                                 "dormers", "chimneys", "style"))
    if "palette" in f:
        b["palette"] = f["palette"]
    b["d"] = f["depth"]
    b["faces"] = {"front": f["els"]}
    if "chimney_at" in f:
        b["chimney_at"] = f["chimney_at"]
    b["faces"]["front"] = _take_dormers(b, f["els"], f["h"])
    for k in ("name", "color"):
        if k in f:
            b[k] = f[k]
    return b


def _stair(part, path, m=1.0):
    """Straight stair (w wide, climbing along +y) or spiral stair (radius r about a core column,
    climbing counter-clockwise from +x). Steps follow h: risers of about 0.17 m."""
    _unknown(part, ("type", "name", "at", "rot", "color") + _KEYS["stair"], path)
    s = {
        "kind": part.get("kind", "straight"),
        "h": _num(part.get("h"), path + ".h", positive=True),
        "per_m": m,
        "at": _vec(part.get("at", [0, 0, 0]), path + ".at", 3),
        "rot": _num(part.get("rot", 0), path + ".rot", -360, 360),
        "rail": part.get("rail", "both"),
    }
    if s["kind"] not in ("straight", "spiral"):
        _fail(path + ".kind", "expected straight or spiral")
    if s["rail"] not in ("both", "left", "right", "outer", "none"):
        _fail(path + ".rail", "expected both, left, right, outer or none")
    other = ("r", "core", "step") if s["kind"] == "straight" else ("w", "tread")
    for key in other:
        if key in part:
            _fail("%s.%s" % (path, key), "not used by a %s stair" % s["kind"])
    s["n"] = max(2, int(round(s["h"] / (0.17 * m))))
    if s["n"] > 200:
        _fail(path + ".h", "more than 200 steps")
    if s["kind"] == "straight":
        s["w"] = _num(part.get("w", 1.0 * m), path + ".w", positive=True)
        s["tread"] = _num(part.get("tread", 0.28 * m), path + ".tread", positive=True)
    else:
        s["r"] = _num(part.get("r", 0.9 * m), path + ".r", positive=True)
        s["core"] = _num(part.get("core", 0.1 * m), path + ".core", positive=True)
        s["step"] = _num(part.get("step", 25), path + ".step", 5, 90)
        if s["core"] >= s["r"] * 0.8:
            _fail(path + ".core", "the core must be well inside r")
    if "name" in part:
        if not isinstance(part["name"], str) or not NAME_RE.match(part["name"]):
            _fail(path + ".name", "1-64 chars of letters, digits, space, _ . -")
        s["name"] = part["name"]
    return s


def _column(part, path, m=1.0):
    """A classical column (or a row of them): plinth, base, shaft with entasis, capital of the
    given order. d defaults to h divided by the order's ratio."""
    _unknown(part, ("type", "name", "at", "rot") + _KEYS["column"], path)
    c = {"order": part.get("order", "tuscan"), "h": _num(part.get("h"), path + ".h", positive=True), "per_m": m,
         "at": _vec(part.get("at", [0, 0, 0]), path + ".at", 3), "rot": _num(part.get("rot", 0), path + ".rot", -360, 360)}
    if c["order"] not in ORDERS:
        _fail(path + ".order", "expected one of %s" % ", ".join(sorted(ORDERS)))
    c["d"] = _num(part.get("d", c["h"] / ORDERS[c["order"]]), path + ".d", positive=True)
    if c["d"] > c["h"] / 3.0:
        _fail(path + ".d", "a column is at least three diameters tall")
    c["count"] = _int(part.get("count", 1), path + ".count", 1, 50)
    c["spacing"] = _num(part.get("spacing", 3.0 * c["d"]), path + ".spacing", positive=True)
    if c["count"] > 1 and c["spacing"] < 1.4 * c["d"]:
        _fail(path + ".spacing", "columns closer than their plinths")
    c["axis"] = part.get("axis", "x")
    if c["axis"] not in ("x", "y"):
        _fail(path + ".axis", "expected x or y")
    if "name" in part:
        if not isinstance(part["name"], str) or not NAME_RE.match(part["name"]):
            _fail(path + ".name", "1-64 chars of letters, digits, space, _ . -")
        c["name"] = part["name"]
    return c


def validate(spec):
    """Returns a normalised spec: {v, units, layer, clear, parts:[primitive...]}.

    Arrays and buildings are expanded here, so the Rhino side only ever sees primitives.
    """
    from .plan import clipped_elements, dropped_elements, plan_block, plan_building, plan_column, plan_facade, plan_stair  # acyclic graph

    if not isinstance(spec, dict):
        _fail("spec", "expected a JSON object")
    _unknown(spec, ("v", "units", "layer", "clear", "parts", "lang"), "spec")
    lang = spec.get("lang", "en")
    if lang not in ("en", "it"):
        _fail("spec.lang", "expected en or it")
    if spec.get("v", VERSION) != VERSION:
        _fail("spec.v", "unsupported version, expected %d" % VERSION)
    units = spec.get("units", "m")
    if units not in UNITS:
        _fail("spec.units", "expected one of %s" % ", ".join(UNITS))
    layer = spec.get("layer", "Model")
    if not isinstance(layer, str) or not NAME_RE.match(layer):
        _fail("spec.layer", "1-64 chars of letters, digits, space, _ . -")
    clear = spec.get("clear", False)
    if not isinstance(clear, bool):
        _fail("spec.clear", "expected true or false")
    parts_in = spec.get("parts")
    if not isinstance(parts_in, list) or not parts_in:
        _fail("spec.parts", "expected a non-empty list")

    parts, notes = [], []
    for i, p in enumerate(parts_in):
        path = "parts[%d]" % i
        t = p.get("type") if isinstance(p, dict) else None
        if t == "array":
            parts.extend(_array(p, path))
        elif t == "building":
            parts.extend(plan_building(_building(p, path, PER_M[units])))
        elif t == "facade":
            f = _facade(p, path, PER_M[units])
            if _needs_block(f):
                b = _as_block(f)
                parts.extend(plan_block(b))
                fe = dict(f, els=b["faces"]["front"])
            else:
                parts.extend(plan_facade(f))
                fe = f
            lost, cut = dropped_elements(fe), clipped_elements(fe)
            if lost:
                notes.append("%s: %d element(s) outside the facade outline not built (above the eaves: "
                             "k pediment, top for a gable, or raise px/h)" % (path, lost))
            if cut:
                notes.append("%s: %d element(s) cut off at the facade outline (check px, h and top)" % (path, cut))
        elif t == "block":
            b = _block(p, path, PER_M[units])
            parts.extend(plan_block(b))
            for key, els in sorted(b["faces"].items()):
                fe = {"w": b["w"] if key in ("front", "back") else b["d"], "h": b["h"], "per_m": b["per_m"], "els": els}
                lost, cut = dropped_elements(fe), clipped_elements(fe)
                if lost:
                    notes.append("%s.faces.%s: %d element(s) outside the face not built (above the eaves: "
                                 "k pediment, or a pitched roof for dormers)" % (path, key, lost))
                if cut:
                    notes.append("%s.faces.%s: %d element(s) cut off at the face outline" % (path, key, cut))
        elif t == "stair":
            parts.extend(plan_stair(_stair(p, path, PER_M[units])))
        elif t == "column":
            parts.extend(plan_column(_column(p, path, PER_M[units])))
        else:
            parts.append(_primitive(p, path))
        if len(parts) > MAX_PARTS:
            _fail(path, "model exceeds the %d part limit" % MAX_PARTS)
    out = {"v": VERSION, "units": units, "layer": layer, "clear": clear, "lang": lang, "parts": parts}
    if notes:
        out["notes"] = notes[:10]
    return out
