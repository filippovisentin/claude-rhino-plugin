# -*- coding: utf-8 -*-
"""Turns a validated building description into plain primitives (slabs, walls, openings, roof).

Pure math, no Rhino: the result goes through the same builder as every other part.

Frames: a box occupies [0,sx] x [0,sy] x [0,sz] from its "at" point and turns by "rot" degrees
around the vertical axis through "at". A prism profile lies in the local XZ plane and is
extruded along local +Y. Cut parts use world coordinates, like any other part.
"""
from __future__ import division

import math

from .naming import ELEMENT_CATEGORY
from .spec import FACES, SpecError, polygon_area

EPS = 1e-6


def _ccw(pts):
    return pts if polygon_area(pts) > 0 else list(reversed(pts))


def _named(base, suffix):
    return "%s %s" % (base, suffix) if base else suffix


def _with_color(part, b):
    if "color" in b:
        part["color"] = b["color"]
    return part


def plan_building(b):
    ax, ay, az = b["at"]
    fp = _ccw(b["footprint"])
    n = len(fp)
    wall_h = b["floor_h"] - b["slab_t"]
    name = b.get("name", "")
    parts = []

    for k in range(b["floors"]):
        z0 = az + k * b["floor_h"]
        parts.append(_with_color({
            "type": "extrude", "name": _named(name, "slab %d" % k), "at": [ax, ay, z0], "rot": 0.0,
            "pts": fp, "h": b["slab_t"],
        }, b))
        for i in range(n):
            p0, p1 = fp[i], fp[(i + 1) % n]
            dx, dy = p1[0] - p0[0], p1[1] - p0[1]
            length = math.hypot(dx, dy)
            if length < EPS:
                continue
            ux, uy = dx / length, dy / length   # along the wall
            nx, ny = -uy, ux                    # inward normal for a CCW footprint
            angle = math.degrees(math.atan2(dy, dx))
            wall = {
                "type": "box", "name": _named(name, "wall %d.%d" % (k, i)),
                "at": [ax + p0[0], ay + p0[1], z0 + b["slab_t"]], "rot": angle,
                "size": [length, b["wall_t"], wall_h],
            }
            cuts = []
            for j, o in enumerate(b["openings"]):
                if o["wall"] != i or (o["floor"] != "all" and o["floor"] != k):
                    continue
                if o["sill"] + o["height"] > wall_h + EPS:
                    raise SpecError("openings[%d]: sill + height %.3g exceeds wall height %.3g"
                                    % (j, o["sill"] + o["height"], wall_h))
                for c in range(o["count"]):
                    x = o["offset"] + c * (o["width"] + o["gap"])
                    if x + o["width"] > length + EPS:
                        raise SpecError("openings[%d]: copy %d ends at %.3g, past wall %d length %.3g"
                                        % (j, c, x + o["width"], i, length))
                    # Start half a wall thickness outside, span two thicknesses: a clean through-cut.
                    cuts.append({
                        "type": "box", "rot": angle,
                        "at": [ax + p0[0] + ux * x - nx * b["wall_t"] * 0.5,
                               ay + p0[1] + uy * x - ny * b["wall_t"] * 0.5,
                               z0 + b["slab_t"] + o["sill"]],
                        "size": [o["width"], b["wall_t"] * 2, o["height"]],
                    })
            if cuts:
                wall["cut"] = cuts
            parts.append(_with_color(wall, b))

    top = az + b["floors"] * b["floor_h"]
    if b["roof"] in ("flat", "gable"):
        parts.append(_with_color({
            "type": "extrude", "name": _named(name, "roof slab"), "at": [ax, ay, top], "rot": 0.0,
            "pts": fp, "h": b["slab_t"],
        }, b))
    if b["roof"] == "gable":
        # Gable over the footprint's bounding box, ridge along the longer side.
        xs = [p[0] for p in fp]
        ys = [p[1] for p in fp]
        minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
        w, d = maxx - minx, maxy - miny
        z = top + b["slab_t"]
        if w >= d:   # ridge along X: profile across Y, rot -90 maps local x -> -Y, local y -> +X
            roof = {"at": [ax + minx, ay + maxy, z], "rot": -90.0,
                    "pts": [[0, 0], [d, 0], [d / 2.0, b["roof_h"]]], "len": w}
        else:        # ridge along Y: profile across X, extruded along +Y
            roof = {"at": [ax + minx, ay + miny, z], "rot": 0.0,
                    "pts": [[0, 0], [w, 0], [w / 2.0, b["roof_h"]]], "len": d}
        roof.update({"type": "prism", "name": _named(name, "roof")})
        parts.append(_with_color(roof, b))
    obj = name or "building"
    for p in parts:
        word = p["name"][len(name):].split()[0] if name else p["name"].split()[0]
        p["obj"] = obj
        p["cat"] = {"slab": "floors", "wall": "walls", "roof": "roof"}[word]
    return parts


# ---------------------------------------------------------------------------------------------
# Facades
#
# Facade frame: u runs along the facade (local +x), v up (+z), depth d into the building (+y).
# The front face is d = 0, so projecting elements (cornices, balconies) sit at negative d.
# Element boxes are [u, v, w, h] in metres from the facade's bottom-left corner, the same layout
# as an annotated photo, which keeps image-to-3D a near 1:1 transcription.
# ---------------------------------------------------------------------------------------------

MIN_EL = 0.01        # elements smaller than 1 cm after clipping are dropped
FRAME = 0.06         # window and door frame width
GLASS_T = 0.02
BAR_W = 0.04
COLORS = {
    "wall": "#e8e2d6", "frame": "#f4f4f2", "glass": "#8fb3cf", "door": "#6b4a2f", "shop": "#8fb3cf",
    "cornice": "#d6cdbb", "molding": "#ddd5c4", "pillar": "#dcd3c1", "sill": "#cfc6b4",
    "blind": "#3e3e3e", "deco": "#cbbfa6", "balcony": "#d6cdbb", "rustic": "#d9cfbd", "quoin": "#d3c9b5",
    "spandrel": "#3b4048", "pediment": "#d6cdbb", "arcade": "#e1dacb",
}
# Default depth per class: recess for openings, projection for everything else.
DEPTH = {"window": 0.12, "door": 0.15, "shop": 0.10, "cornice": 0.30, "molding": 0.06,
         "pillar": 0.12, "sill": 0.06, "blind": 0.04, "deco": 0.04, "balcony": 1.0, "rustic": 0.03, "quoin": 0.04,
         "spandrel": 0.03, "pediment": 0.5, "arcade": 3.0}


OPENING_SHAPES = ("rect", "arch", "seg", "round")
ROUND_SEGMENTS = 24
HOOD_SHAPES = ("flat", "tri", "seg")
ARC_SEGMENTS = 12


def arc_rise(shape, w, h):
    """Height of the curved top of an opening: semicircle for arch, a flat arc for seg."""
    if shape == "arch":
        return min(w / 2.0, h * 0.6)
    if shape == "seg":
        return min(w * 0.15, h * 0.4)
    return 0.0


def opening_outline(u, v, w, h, shape="rect"):
    """Closed outline [[u, v], ...] (counter-clockwise, not repeated) of an opening in the facade
    plane. Curved tops are polylines; the bounding box is exactly [u, v, w, h]. round: the ellipse
    inscribed in the box (a circle when it is square), starting at the bottom."""
    if shape == "round":
        return [[u + w / 2.0 + w / 2.0 * math.sin(2 * math.pi * i / ROUND_SEGMENTS),
                 v + h / 2.0 - h / 2.0 * math.cos(2 * math.pi * i / ROUND_SEGMENTS)] for i in range(ROUND_SEGMENTS)]
    rise = arc_rise(shape, w, h)
    if rise <= 0:
        return [[u, v], [u + w, v], [u + w, v + h], [u, v + h]]
    spring = v + h - rise
    pts = [[u, v], [u + w, v], [u + w, spring]]
    if shape == "arch":   # half ellipse: a semicircle when rise = w / 2
        for i in range(1, ARC_SEGMENTS):
            a = math.pi * i / ARC_SEGMENTS
            pts.append([u + w / 2.0 + w / 2.0 * math.cos(a), spring + rise * math.sin(a)])
    else:                 # circular segment through both springs and the crown
        R = (w * w / 4.0 + rise * rise) / (2.0 * rise)
        cx, cy = u + w / 2.0, spring + rise - R
        half = math.asin(min(1.0, (w / 2.0) / R))
        for i in range(1, ARC_SEGMENTS):
            a = math.pi / 2 - half + 2 * half * i / ARC_SEGMENTS   # right spring -> left: stays CCW
            pts.append([cx + R * math.cos(a), cy + R * math.sin(a)])
    pts.append([u, spring])
    return pts


def _expanded(f):
    for el in f["els"]:
        u0, v0, w, h = el["box"]
        nx, ny, du, dv = el["grid"]
        offsets = el.get("offs") or [[i * du, j * dv] for j in range(ny) for i in range(nx)]
        for ou, ov in offsets:
            yield el, u0 + ou, v0 + ov, w, h


def pediment_boxes(f):
    """[u, v, w, h] of every pediment: they rise above the eaves, so they are not clipped there."""
    return [[u, v, w, h] for el, u, v, w, h in _expanded(f) if el["k"] == "pediment"]


def in_pediment(r, peds, tol=1e-6):
    """The pediment box holding r (an oculus, a relief in the tympanum), or None."""
    u, v, w, h = r
    for pu, pv, pw, ph in peds:
        if u >= pu - tol and u + w <= pu + pw + tol and v >= pv - tol and v + h <= pv + ph + tol:
            return [pu, pv, pw, ph]
    return None


def facade_elements(f):
    """Expands grids and clips every element to the facade (pediments, and what sits inside
    them, may rise above it). Returns [(k, [u, v, w, h], el)]."""
    out = []
    peds = pediment_boxes(f)
    min_el = MIN_EL * f.get("per_m", 1.0)
    for el, u, v, w, h in _expanded(f):
        top = f["h"]
        if el["k"] == "pediment" or in_pediment([u, v, w, h], peds):
            top = max(top, v + h)
        cu0, cv0 = max(u, 0.0), max(v, 0.0)
        cu1, cv1 = min(u + w, f["w"]), min(v + h, top)
        if cu1 - cu0 >= min_el and cv1 - cv0 >= min_el:
            out.append((el["k"], [cu0, cv0, cu1 - cu0, cv1 - cv0], el))
    return out


def dropped_elements(f):
    """How many element boxes fall wholly outside the facade (and so are not built)."""
    return sum(1 for _ in _expanded(f)) - len(facade_elements(f))


def _merge_rects(rects):
    """Merges overlapping rectangles into their bounding boxes until none overlap."""
    # Each pass folds every rectangle into the first kept one it overlaps, so a whole chain of
    # overlapping openings collapses in one pass instead of one restart per merge (a spec with a
    # thousand stacked windows must not stall Rhino).
    from .spec import rects_overlap
    rects = [list(r) for r in rects]
    while True:
        kept, changed = [], False
        for r in rects:
            for k in kept:
                if rects_overlap(k, r, MIN_EL):   # touching loops would break the wall face
                    u0, v0 = min(k[0], r[0]), min(k[1], r[1])
                    u1, v1 = max(k[0] + k[2], r[0] + r[2]), max(k[1] + k[3], r[1] + r[3])
                    k[:] = [u0, v0, u1 - u0, v1 - v0]
                    changed = True
                    break
            else:
                kept.append(r)
        rects = kept
        if not changed:
            return rects


SURROUND = 0.15      # classic window and door surround width
PROFILES = {
    # [d, v] as fractions of (projection, height), bottom to top, wall side first and last.
    # Main cornice: bed moulding, dentil band, corona with its soffit, cyma recta, top fillet.
    "main": [(0, 0), (-0.15, 0), (-0.3, 0.12), (-0.35, 0.25), (-0.4, 0.25), (-0.4, 0.45), (-0.9, 0.45),
             (-0.9, 0.78), (-0.95, 0.84), (-1.0, 0.92), (-1.0, 1.0), (0, 1.0)],
    # String course or flat hood: fillet, cyma, fillet.
    "string": [(0, 0), (-0.5, 0), (-0.6, 0.15), (-0.6, 0.35), (-1.0, 0.6), (-1.0, 1.0), (0, 1.0)],
    # Sill: slab with a drip, stepping back underneath.
    "sill": [(0, 0), (-0.6, 0), (-0.6, 0.35), (-1.0, 0.45), (-1.0, 1.0), (0, 1.0)],
}


def _profile(kind, v, h, depth):
    return [[fd * depth, v + fv * h] for fd, fv in PROFILES[kind]]


def _ring(flat, label, outer, inner, d0, depth, color):
    """A band between two closed outlines with the same number of points, as quads."""
    n = len(outer)
    return [flat(label, [outer[a], outer[(a + 1) % n], inner[(a + 1) % n], inner[a]], d0, depth, color)
            for a in range(n)]


def _surround(box, flat, tag, u, v, w, h, sur, k, shape, m):
    """Moulded band around an opening, proud of the wall. On arches the band follows the curve
    (an archivolt, built from short segments) and carries a keystone at the crown; round openings
    get a ring with a keystone."""
    proj = min(0.06 * m, sur / 2.0)
    if shape == "round":
        out = _ring(flat, tag + " surround", opening_outline(u, v, w, h, "round"),
                    opening_outline(u + sur, v + sur, w - 2 * sur, h - 2 * sur, "round"), -proj, proj, COLORS["sill"])
        kw = min(0.25 * m, w / 4.0)
        out.append(box(tag + " keystone", u + (w - kw) / 2.0, -proj * 1.6, v + h - sur * 1.6, kw, proj * 1.6,
                       sur * 1.6, COLORS["sill"]))
        return out
    rise = arc_rise(shape, w, h) if shape in ("arch", "seg") else 0.0
    # The opening inside the band: doors have no band under them.
    ib = [u + sur, v, w - 2 * sur, h - sur] if k == "door" else [u + sur, v + sur, w - 2 * sur, h - 2 * sur]
    if rise and (ib[2] <= 0 or ib[3] <= 0 or arc_rise(shape, ib[2], ib[3]) <= 0 or ib[3] <= arc_rise(shape, ib[2], ib[3])):
        rise = 0.0   # an opening too small for a curved band: straight jambs and head
    jamb_h = h - rise if rise else h
    out = [box(tag + " surround", u, -proj, v, sur, proj, jamb_h, COLORS["sill"]),
           box(tag + " surround", u + w - sur, -proj, v, sur, proj, jamb_h, COLORS["sill"])]
    if rise:
        outer = opening_outline(u, v, w, h, shape)[2:]                       # right spring -> left spring
        inner = opening_outline(ib[0], ib[1], ib[2], ib[3], shape)[2:]
        for a in range(len(outer) - 1):
            quad = [outer[a], outer[a + 1], inner[a + 1], inner[a]]
            out.append(flat(tag + " surround", quad, -proj, proj, COLORS["sill"]))
    else:
        out.append(box(tag + " surround", u + sur, -proj, v + h - sur, w - 2 * sur, proj, sur, COLORS["sill"]))
    if k != "door":
        out.append(box(tag + " surround", u + sur, -proj, v, w - 2 * sur, proj, sur, COLORS["sill"]))
    if shape in ("arch", "seg"):
        kw = min(0.25 * m, w / 4.0)
        out.append(box(tag + " keystone", u + (w - kw) / 2.0, -proj * 1.6, v + h - sur * 1.6, kw, proj * 1.6,
                       sur * 1.6 + 0.04 * m, COLORS["sill"]))
    return out


def _balcony(box, along, tag, u, v, w, h, depth, rail, classic, m):
    """Slab, consoles underneath (classic) and a railing: balustrade, iron bars, solid parapet, or
    glass panes between slim metal posts."""
    slab_t = min(0.15 * m, h)
    out = [box(tag + " slab", u, -depth, v, w, depth, slab_t, COLORS["balcony"])]
    if classic:
        n = max(2, int(round(w / (0.9 * m))) + 1)
        cw, ch = min(0.22 * m, w / (2.0 * n)), min(0.6 * m, depth * 0.8)
        for i in range(n):
            cu = u + 0.1 * m + (w - 0.2 * m - cw) * i / float(n - 1)
            pts = [[0, v - ch], [0, v], [-0.85 * depth, v], [-0.85 * depth, v - 0.12 * m], [-0.2 * m, v - ch]]
            out.append(along(tag + " console", cu, cw, pts, COLORS["balcony"]))
    rail_h = h - slab_t
    if rail_h <= 0.05 * m:
        return out
    z = v + slab_t
    t = min(0.15 * m if rail == "balustrade" else 0.05 * m, w / 4.0, depth / 2.0)
    if rail == "solid":
        out.append(box(tag + " parapet", u, -depth, z, w, t, rail_h, COLORS["balcony"]))
        for side_u in (u, u + w - t):
            out.append(box(tag + " parapet", side_u, -depth + t, z, t, depth - t, rail_h, COLORS["balcony"]))
        return out
    runs = [(u, -depth, w, t), (u, -depth + t, t, depth - t), (u + w - t, -depth + t, t, depth - t)]
    if rail == "glass":
        # Panes set 4 cm above the slab, posts about every 1.2 m and a handrail, all metal.
        top_h, gap, pw = min(0.05 * m, rail_h / 5.0), min(0.04 * m, rail_h / 6.0), min(0.04 * m, t)
        for ru, rd, rw, rdep in runs:
            length = max(rw, rdep)
            along_u = rw >= rdep
            out.append(box(tag + " handrail iron", ru, rd, z + rail_h - top_h, rw, rdep, top_h, COLORS["blind"]))
            n = max(1, int(round(length / (1.2 * m))))
            for i in range(n + 1):
                off = min(max(0.0, length * i / float(n) - pw / 2.0), length - pw)
                pu, pd = (ru + off, rd) if along_u else (ru, rd + off)
                out.append(box(tag + " post iron", pu, pd, z, pw if along_u else rw, rdep if along_u else pw,
                               rail_h - top_h, COLORS["blind"]))
            pane_t = min(0.02 * m, min(rw, rdep) / 2.0)
            if along_u:
                out.append(box(tag + " pane glass", ru, rd + (rdep - pane_t) / 2.0, z + gap, rw, pane_t,
                               rail_h - top_h - gap, COLORS["glass"]))
            else:
                out.append(box(tag + " pane glass", ru + (rw - pane_t) / 2.0, rd, z + gap, pane_t, rdep,
                               rail_h - top_h - gap, COLORS["glass"]))
        return out
    top_h = min((0.12 if rail == "balustrade" else 0.04) * m, rail_h / 4.0)
    iron = " iron" if rail == "iron" else ""
    plinth_h = min(0.15 * m, rail_h / 5.0) if rail == "balustrade" else 0.0
    # Front run along u, then the two sides back to the wall: plinth, handrail, posts between.
    for ru, rd, rw, rdep in runs:
        if plinth_h:
            out.append(box(tag + " plinth", ru, rd, z, rw, rdep, plinth_h, COLORS["balcony"]))
        out.append(box(tag + " handrail" + iron, ru, rd, z + rail_h - top_h, rw, rdep, top_h, COLORS["balcony"]))
    post_h = rail_h - top_h - plinth_h
    step = (0.25 if rail == "balustrade" else 0.12) * m
    pw = (0.11 if rail == "balustrade" else 0.016) * m
    for ru, rd, rw, rdep in runs:
        length = max(rw, rdep)
        count = max(1, int(length // step))
        for i in range(count):
            off = (i + 0.5) * length / count - pw / 2.0
            pu, pd = (ru + off, rd + (rdep - pw) / 2.0) if rw >= rdep else (ru + (rw - pw) / 2.0, rd + off)
            out.append(box(tag + (" baluster" if rail == "balustrade" else " bar iron"), pu, pd, z + plinth_h,
                           pw, pw, post_h, COLORS["blind"] if rail == "iron" else COLORS["balcony"]))
    return out


def _door(box, flat, tag, u, v, w, h, r, shape, m):
    """Door inside its frame: one leaf, or two when wider than 1.3 m, each with two raised panels;
    a glazed fanlight in the arch, or above a transom when the door is taller than 2.7 m."""
    rise = arc_rise(shape, w, h) if shape in ("arch", "seg") else 0.0
    fan = rise if rise else (min(0.8 * m, h - 2.3 * m) if h > 2.7 * m else 0.0)
    lh = h - fan
    d0 = r + 0.03 * m
    out = []
    n = 2 if w > 1.3 * m else 1
    gap = 0.01 * m
    lw = (w - gap * (n - 1)) / n
    mg = min(0.12 * m, lw / 5.0)
    for i in range(n):
        lu = u + i * (lw + gap)
        out.append(box(tag + " leaf", lu, d0, v, lw, 0.05 * m, lh, COLORS["door"]))
        if lh > 1.2 * m and lw > 3 * mg:
            for f0, f1 in ((0.08, 0.42), (0.5, 0.92)):
                out.append(box(tag + " leaf", lu + mg, d0 - 0.02 * m, v + lh * f0, lw - 2 * mg, 0.02 * m,
                               lh * (f1 - f0), COLORS["door"]))
    if fan > MIN_EL * m:
        bar = min(BAR_W * 1.5 * m, fan / 4.0)
        out.append(box(tag + " bar", u, d0 - 0.01 * m, v + lh, w, 0.06 * m, bar, COLORS["frame"]))
        if rise:
            pts = [q for q in opening_outline(u, v, w, h, shape)[2:]]
            pts = [[p[0], max(p[1], v + lh + bar)] for p in pts]
            out.append(flat(tag + " glass", pts, d0, GLASS_T * m, COLORS["glass"]))
        else:
            out.append(box(tag + " glass", u, d0, v + lh + bar, w, GLASS_T * m, fan - bar, COLORS["glass"]))
    return out


def _shutter(box, along, tag, u, v, w, h, depth, m):
    """Louvred shutter: stiles, top and bottom rails, and the louvres between them as one sawtooth
    profile (a slat every 10 cm, tilted out at the bottom). One prism instead of a part per slat
    keeps a palazzo with 80 shutters far below the part limit."""
    st = min(0.05 * m, w / 6.0)
    rail = min(0.06 * m, h / 10.0)
    out = [box(tag, u, -depth, v, st, depth, h, COLORS["blind"]),
           box(tag, u + w - st, -depth, v, st, depth, h, COLORS["blind"]),
           box(tag, u + st, -depth, v, w - 2 * st, depth, rail, COLORS["blind"]),
           box(tag, u + st, -depth, v + h - rail, w - 2 * st, depth, rail, COLORS["blind"])]
    v0, v1 = v + rail, v + h - rail
    n = max(1, min(30, int((v1 - v0) // (0.10 * m))))
    pitch = (v1 - v0) / n
    back, mid, front = -0.2 * depth, -0.5 * depth, -0.8 * depth
    pts = [[back, v1], [mid, v1]]
    for i in range(n):   # down the front: each slat leans out to its lower edge
        top = v1 - i * pitch
        pts += [[front, top - 0.8 * pitch], [mid, top - pitch]]
    pts.append([back, v0])
    out.append(along(tag + " slats", u + st, w - 2 * st, pts, COLORS["blind"]))
    return out


def _quoins(box, tag, u, v, w, h, depth, right, m):
    """Corner stones: courses 0.45 high, alternately the full box width and 60 % of it, flush with
    the corner side of the box (right when the box sits in the facade's right half)."""
    n = max(1, int(round(h / (0.45 * m))))
    ch = h / n
    gap = min(0.03 * m, ch * 0.15)
    out = []
    for i in range(n):
        bw = w if i % 2 == 0 else w * 0.6
        bu = u + w - bw if right else u
        out.append(box(tag, bu, -depth, v + i * ch, bw, depth, ch - gap, COLORS["quoin"]))
    return out


def _rustication(box, tag, u, v, w, h, depth, openings, m):
    """Courses of stone 0.45 high separated by 4 cm grooves, interrupted by the openings."""
    course = 0.45 * m
    n = max(1, int(round(h / course)))
    ch = h / n
    groove = min(0.04 * m, ch * 0.15)   # a band lower than one groove still gets a course
    out = []
    for i in range(n):
        z0, z1 = v + i * ch, v + (i + 1) * ch - groove
        spans = [(u, u + w)]
        for ou, ov, ow, oh in openings:
            if ov < z1 and ov + oh > z0:
                nxt = []
                for a, b in spans:
                    if ou >= b or ou + ow <= a:
                        nxt.append((a, b))
                        continue
                    if ou > a:
                        nxt.append((a, ou))
                    if ou + ow < b:
                        nxt.append((ou + ow, b))
                spans = nxt
        for a, b in spans:
            if b - a > 0.05 * m:
                out.append(box(tag, a, -depth, z0, b - a, depth, z1 - z0, COLORS["rustic"]))
    return out


def plan_facade(f):
    ax, ay, az = f["at"]
    rot = f["rot"]
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    W, H, T = f["w"], f["h"], f["t"]
    name = f.get("name", "facade")
    wall_color = f.get("color", COLORS["wall"])

    def place(u, d, v):
        return [ax + c * u - s * d, ay + s * u + c * d, az + v]

    def box(label, u, d, v, w, depth, h, color):
        return {"type": "box", "name": _named(name, label), "at": place(u, d, v), "rot": rot,
                "size": [w, depth, h], "color": color}

    m = f.get("per_m", 1.0)          # spec units per metre: detail sizes are real-world metres
    FRAME_, GLASS_, BAR_, MIN_ = FRAME * m, GLASS_T * m, BAR_W * m, MIN_EL * m
    classic = f.get("style", "plain") == "classic"
    modern = f.get("style") == "modern"
    if modern:   # slim aluminium profiles
        FRAME_, BAR_ = 0.04 * m, 0.025 * m
    els = []
    for k, r, el in facade_elements(f):
        # The read box is the opening (glass and frame, as photos are annotated); the moulded
        # surround goes around it, narrowed where the facade edge leaves less room. Doors keep
        # their foot on the ground line. (Carving the surround inside the box made classic
        # windows about half the size they are in the photo.)
        sur = el.get("sur", SURROUND * m if classic and k in ("window", "door") else 0.0)
        u, v, w, h = r
        if sur > 0:
            room = [u, W - u - w, H - v - h] + ([] if k == "door" else [v])
            sur = min([sur] + room)
        if sur > MIN_:
            inner = r
            r = [u - sur, v if k == "door" else v - sur, w + 2 * sur, h + sur if k == "door" else h + 2 * sur]
        else:
            sur, inner = 0.0, r
        if k == "shop" and inner[3] >= 2.4 * m:
            fh = min(0.6 * m, 0.2 * inner[3])
            inner = inner[:3] + [inner[3] - fh]
        els.append((k, r, el, sur, inner))
    raw = [(inner, el.get("shape", "rect")) for k, r, el, sur, inner in els if k in ("window", "door", "shop", "arcade")]
    key = lambda r: tuple(round(x, 9) for x in r)
    shape_of = dict((key(r), sh) for r, sh in raw)
    # Merged openings keep their shape only when nothing was merged into them.
    openings = [(r, shape_of.get(key(r), "rect")) for r in _merge_rects([r for r, _ in raw])]
    eps = 1e-3 * m
    inside = lambda r: r[0] > eps and r[1] > eps and r[0] + r[2] < W - eps and r[1] + r[3] < H - eps
    holes = [r + [OPENING_SHAPES.index(sh)] if sh != "rect" else r for r, sh in openings if inside(r)]
    edge = [(r, sh) for r, sh in openings if not inside(r) and r[1] < H - eps]   # none above the eaves

    wall = {"type": "panel", "name": _named(name, "wall"), "at": place(0, 0, 0), "rot": rot,
            "size": [W, H], "t": T, "holes": holes, "color": wall_color}
    if edge:
        # Openings touching the facade outline (shop fronts, doors on the ground line) can't be
        # inner loops of an extrusion: cut them with their outline instead, slightly oversized.
        wall["cut"] = [{"type": "prism", "at": place(0, -T, 0), "rot": rot, "len": 3 * T,
                        "pts": opening_outline(r[0] - eps, r[1] - eps, r[2] + 2 * eps, r[3] + 2 * eps, sh)}
                       for r, sh in edge]
    parts = [wall]
    rot90 = _wrap(rot + 90.0)

    def along(label, u, w, pts, color):
        """A profile [[d, v], ...] (d < 0 projects out of the wall) run along the facade from u
        to u + w: rot + 90 turns the prism's local x into depth and its local y into -u."""
        return {"type": "prism", "name": _named(name, label), "at": place(u + w, 0, 0), "rot": rot90,
                "len": w, "pts": [[d, vv] for d, vv in pts], "color": color}

    def flat(label, pts, d0, depth, color):
        """An outline [[u, v], ...] in the facade plane, from depth d0 to d0 + depth."""
        return {"type": "prism", "name": _named(name, label), "at": place(0, d0, 0), "rot": rot,
                "len": depth, "pts": pts, "color": color}

    opening_boxes = [r for k, r, el, sur, inner in els if k in ("window", "door", "shop")]
    marks = []   # (first part index, tag) per element: its parts are joined into one solid per layer
    for n, (k, (u, v, w, h), el, sur, inner) in enumerate(els):
        tag = "%s %d" % (k, n)
        depth = el.get("d", DEPTH[k] * m)
        marks.append((len(parts), tag, k, [u, v, w, h], depth))
        shape = el.get("shape")
        if k in ("window", "door", "shop"):
            if sur > 0:
                parts.extend(_surround(box, flat, tag, u, v, w, h, sur, k, shape, m))
            fh = v + h - sur - (inner[1] + inner[3])
            if k == "shop" and fh > MIN_:   # the fascia above a shop front carries its sign
                parts.append(box(tag + " sign", u + sur, -0.08 * m, v + h - sur - fh, w - 2 * sur, 0.08 * m, fh,
                                 COLORS["frame"]))
            u, v, w, h = inner
        if k == "window" and shape == "round":
            # Oculus: a ring frame and round glass, set back in the wall like any window.
            r = min(depth, T - GLASS_ * 2)
            fr = min(FRAME_, w / 4.0, h / 4.0)
            if w - 2 * fr < MIN_ or h - 2 * fr < MIN_:
                continue
            ring_in = opening_outline(u + fr, v + fr, w - 2 * fr, h - 2 * fr, "round")
            parts.extend(_ring(flat, tag + " frame", opening_outline(u, v, w, h, "round"), ring_in, r,
                               min(0.08 * m, T - r), COLORS["frame"]))
            parts.append(flat(tag + " glass", ring_in, r + 0.03 * m, GLASS_, COLORS["glass"]))
        elif k in ("window", "door", "shop") and shape in ("arch", "seg"):
            r = min(depth, T - GLASS_ * 2)
            fr = min(FRAME_, w / 4.0, h / 4.0)
            iu, iv, iw, ih = u + fr, v + fr, w - 2 * fr, h - 2 * fr
            if iw < MIN_ or ih < MIN_:
                continue
            if k == "door":
                parts.extend(_door(box, flat, tag, iu, iv, iw, ih, r, shape, m))
                continue
            leaf = COLORS["door"] if k == "door" else COLORS["glass"]
            parts.append({"type": "prism", "name": _named(name, tag + (" leaf" if k == "door" else " glass")),
                          "at": place(0, r + 0.03 * m, 0), "rot": rot, "len": 0.05 * m if k == "door" else GLASS_,
                          "pts": opening_outline(iu, iv, iw, ih, shape), "color": leaf})
            spring_h = ih - arc_rise(shape, iw, ih)   # bars stop where the curve starts
            nb_v, nb_h = el.get("bars", [0, 0])
            for b in range(nb_v):
                bu = iu + iw * (b + 1) / (nb_v + 1.0) - BAR_ / 2
                parts.append(box(tag + " bar", bu, r + 0.02 * m, iv, BAR_, 0.04 * m, spring_h, COLORS["frame"]))
            for b in range(nb_h):
                bv = iv + spring_h * (b + 1) / (nb_h + 1.0) - BAR_ / 2
                parts.append(box(tag + " bar", iu, r + 0.02 * m, bv, iw, 0.04 * m, BAR_, COLORS["frame"]))
        elif k in ("window", "door", "shop"):
            r = min(depth, T - GLASS_ * 2)      # recess, kept inside the wall
            fr = min(FRAME_, w / 4.0, h / 4.0)
            if w > 2 * fr + MIN_ and h > 2 * fr + MIN_:
                ft = 0.08 * m
                parts.append({"type": "panel", "name": _named(name, tag + " frame"), "at": place(u, r, v),
                              "rot": rot, "size": [w, h], "t": ft if r + ft < T else T - r,
                              "holes": [[fr, fr, w - 2 * fr, h - 2 * fr]], "color": COLORS["frame"]})
            iu, iv, iw, ih = u + fr, v + fr, w - 2 * fr, h - 2 * fr
            if iw < MIN_ or ih < MIN_:
                continue
            if k == "door" and not modern:
                parts.extend(_door(box, flat, tag, iu, iv, iw, ih, r, "rect", m))
                continue
            glazed = k != "door" or modern   # modern doors are glass in a slim frame
            leaf = COLORS["glass"] if glazed else COLORS["door"]
            leaf_t = GLASS_ if glazed else 0.05 * m
            parts.append(box(tag + (" glass" if glazed else " leaf"), iu, r + 0.03 * m, iv, iw, leaf_t, ih, leaf))
            nb_v, nb_h = el.get("bars", [0, 0])
            for b in range(nb_v):
                bu = iu + iw * (b + 1) / (nb_v + 1.0) - BAR_ / 2
                parts.append(box(tag + " bar", bu, r + 0.02 * m, iv, BAR_, 0.04 * m, ih, COLORS["frame"]))
            for b in range(nb_h):
                bv = iv + ih * (b + 1) / (nb_h + 1.0) - BAR_ / 2
                parts.append(box(tag + " bar", iu, r + 0.02 * m, bv, iw, 0.04 * m, BAR_, COLORS["frame"]))
        elif k == "balcony":
            parts.extend(_balcony(box, along, tag, u, v, w, h, depth, el.get("rail", "balustrade" if classic else "iron"),
                                  classic, m))
        elif k == "arcade":
            pass   # a hole through the wall; its recess is built per row after the loop
        elif k == "pediment":
            # Temple front over a risalit, in any style: raking cornices, a tympanum set back
            # between them and a moulded base, rising above the eaves where the photo shows it.
            bt = min(0.35 * m, h / 4.0)
            dx = bt * w / (2.0 * h)
            top = [u + w / 2.0, v + h]
            parts.append(flat(tag, [[u, v], top, [top[0], top[1] - bt], [u + dx, v]], -depth, depth, COLORS[k]))
            parts.append(flat(tag, [[u + w, v], [u + w - dx, v], [top[0], top[1] - bt], top], -depth, depth, COLORS[k]))
            parts.append(flat(tag + " tympanum", [[u + dx, v], [u + w - dx, v], [top[0], top[1] - bt]],
                              -depth * 0.35, depth * 0.35, COLORS[k]))
            lip = min(0.15 * m, h / 6.0)
            parts.append(along(tag + " base", u - lip, w + 2 * lip, _profile("string", v - lip, lip * 2, depth + lip),
                               COLORS[k]))
        elif k == "cornice" and shape == "tri" and classic and h > 0.1 * m:
            # Pediment: two raking cornices over a tympanum set back between them.
            bt = min(0.12 * m, h / 3.0)
            dx = bt * w / (2.0 * h)
            top = [u + w / 2.0, v + h]
            parts.append(flat(tag, [[u, v], top, [top[0], top[1] - bt], [u + dx, v]], -depth, depth, COLORS[k]))
            parts.append(flat(tag, [[u + w, v], [u + w - dx, v], [top[0], top[1] - bt], top], -depth, depth, COLORS[k]))
            parts.append(flat(tag + " tympanum", [[u + dx, v], [u + w - dx, v], [top[0], top[1] - bt]],
                              -depth * 0.35, depth * 0.35, COLORS[k]))
            lip = min(0.06 * m, h / 4.0)
            parts.append(along(tag + " base", u - lip, w + 2 * lip, _profile("string", v - lip, lip * 2, depth + lip),
                               COLORS[k]))
        elif k == "cornice" and shape in ("tri", "seg"):
            # Pediment: the hood outline in the facade plane, pushed out by its depth.
            if shape == "tri":
                pts = [[u, v], [u + w, v], [u + w / 2.0, v + h]]
            else:
                arc = opening_outline(u, v - h, w, 2 * h, "seg")
                pts = [[u, v], [u + w, v]] + [q for q in arc[2:] if q[1] > v]
            parts.append({"type": "prism", "name": _named(name, tag), "at": place(0, -depth, 0), "rot": rot,
                          "len": depth, "pts": pts, "color": COLORS[k]})
            if classic:   # the pediment's horizontal cornice, a little wider and deeper
                lip = min(0.06 * m, h / 4.0)
                parts.append(along(tag + " base", u - lip, w + 2 * lip, _profile("string", v - lip, lip * 2, depth + lip),
                                   COLORS[k]))
        elif k == "cornice" and h > 0.35 * m and 0.3 * m < w < 4.0 * m:
            # A tall window crown: a frieze panel under a hood moulding (the hood is the top 0.3 m).
            hood = min(0.3 * m, h / 2.0)
            fw = min(0.08 * m, w / 6.0)
            parts.append(box(tag + " frieze", u + fw, -0.04 * m, v, w - 2 * fw, 0.04 * m, h - hood, COLORS[k]))
            if classic:
                parts.append(along(tag, u, w, _profile("string", v + h - hood, hood, depth), COLORS[k]))
            else:
                parts.append(box(tag, u, -depth, v + h - hood, w, depth, hood, COLORS[k]))
        elif k in ("molding", "cornice") and classic and h >= 0.08 * m:
            main = k == "molding" and h >= 0.4 * m and depth >= 0.3 * m
            parts.append(along(tag, u, w, _profile("main" if main else "string", v, h, depth), COLORS[k]))
            if main:   # dentils under the corona
                dw, gap = 0.12 * m, 0.12 * m
                count = int((w - gap) // (dw + gap))
                start = u + (w - count * (dw + gap) + gap) / 2.0
                for i in range(count):
                    parts.append(box(tag + " dentil", start + i * (dw + gap), -0.55 * depth, v + 0.27 * h,
                                     dw, 0.15 * depth, 0.16 * h, COLORS[k]))
        elif k in ("molding", "cornice") and depth >= 0.15 * m and h >= 0.12 * m:
            # Corbelled profile: three steps growing outward toward the top.
            z = v
            for frac_h, frac_d in ((0.4, 0.5), (0.3, 0.8), (0.3, 1.0)):
                parts.append(box(tag, u, -depth * frac_d, z, w, depth * frac_d, h * frac_h, COLORS[k]))
                z += h * frac_h
        elif k == "sill" and h > 0.25 * m and w > 0.3 * m:
            # Sill with its apron: the slab on top, a recessed panel under it down to the box foot.
            slab = min(0.12 * m, h / 3.0)
            fw = min(0.08 * m, w / 6.0)
            if classic:
                parts.append(along(tag, u, w, _profile("sill", v + h - slab, slab, depth), COLORS[k]))
            else:
                parts.append(box(tag, u, -depth, v + h - slab, w, depth, slab, COLORS[k]))
            parts.append(box(tag + " apron", u + fw, -0.04 * m, v, w - 2 * fw, 0.04 * m, h - slab, COLORS[k]))
        elif k == "sill" and classic and h >= 0.04 * m:
            parts.append(along(tag, u, w, _profile("sill", v, h, depth), COLORS[k]))
        elif k == "pillar" and shape == "round":
            # A round shaft (tiled pier, engaged or free column): d is how far it stands out of
            # the wall, the diameter by default (a free column against the facade).
            rr = w / 2.0
            out_d = el.get("d", w)
            cu, cd = u + rr, -(out_d - rr)
            def cyl(label, r_, z, hh):
                return {"type": "cyl", "name": _named(name, label), "at": place(cu, cd, z), "rot": rot,
                        "r": r_, "h": hh, "color": COLORS[k]}
            if classic and h >= 1.5 * m:
                base_h, cap_h = min(0.35 * m, h * 0.08), min(0.4 * m, h * 0.1)
                parts.append(cyl(tag + " base", rr * 1.18, v, base_h))
                parts.append(cyl(tag, rr, v + base_h, h - base_h - cap_h))
                parts.append(cyl(tag + " capital", rr * 1.22, v + h - cap_h, cap_h))
            else:
                parts.append(cyl(tag, rr, v, h))
        elif k == "pillar" and classic and h >= 1.5 * m:
            base_h, cap_h, lip = min(0.35 * m, h * 0.1), min(0.45 * m, h * 0.12), min(0.06 * m, w / 4.0)
            parts.append(box(tag + " base", u - lip, -depth - lip, v, w + 2 * lip, depth + lip, base_h, COLORS[k]))
            parts.append(box(tag, u, -depth, v + base_h, w, depth, h - base_h - cap_h, COLORS[k]))
            parts.append(along(tag + " capital", u - lip, w + 2 * lip, _profile("string", v + h - cap_h, cap_h, depth + lip),
                               COLORS[k]))
        elif k == "blind" and h > 0.6 * m and w > 0.25 * m:
            parts.extend(_shutter(box, along, tag, u, v, w, h, depth, m))
        elif k == "rustic":
            parts.extend(_rustication(box, tag, u, v, w, h, depth, opening_boxes, m))
        elif k == "quoin":
            parts.extend(_quoins(box, tag, u, v, w, h, depth, u + w / 2.0 > W / 2.0, m))
        elif k == "deco" and shape == "console":
            # Bracket: deep at the top where it carries a cornice or sill, tapering down to the wall.
            pts = [[0, v], [-0.35 * depth, v], [-depth, v + 0.7 * h], [-depth, v + h], [0, v + h]]
            parts.append(along(tag, u, w, pts, COLORS[k]))
        elif k == "deco" and shape == "oval":
            # Cartouche or medallion: an elliptical boss in the facade plane.
            n_seg = 16
            pts = [[u + w / 2.0 + w / 2.0 * math.cos(2 * math.pi * i / n_seg),
                    v + h / 2.0 + h / 2.0 * math.sin(2 * math.pi * i / n_seg)] for i in range(n_seg)]
            parts.append({"type": "prism", "name": _named(name, tag), "at": place(0, -depth, 0), "rot": rot,
                          "len": depth, "pts": pts, "color": COLORS[k]})
        elif k == "deco" and shape == "panel":
            # Framed panel: a raised moulding around a sunk field.
            fw = min(0.08 * m, w / 4.0, h / 4.0)
            parts.append({"type": "panel", "name": _named(name, tag), "at": place(u, -depth, v), "rot": rot,
                          "size": [w, h], "t": depth, "holes": [[fw, fw, w - 2 * fw, h - 2 * fw]], "color": COLORS[k]})
            parts.append(box(tag, u + fw, -depth * 0.4, v + fw, w - 2 * fw, depth * 0.4, h - 2 * fw, COLORS[k]))
        else:
            parts.append(box(tag, u, -depth, v, w, depth, h, COLORS[k]))

    ends = [mk[0] for mk in marks[1:]] + [len(parts)]
    peds = pediment_boxes(f)
    ped_d = max([el.get("d", DEPTH["pediment"] * m) for k, r, el, sur, inner in els if k == "pediment"] or [0.0])
    arcades = [(r, el.get("d", DEPTH["arcade"] * m), el.get("shape", "rect")) for k, r, el, sur, inner in els
               if k == "arcade"]
    inside_arcade = {}
    for (start, tag, k, r, depth), end in zip(marks, ends):
        # An oculus or a relief inside a pediment stands on its tympanum, in front of the wall line
        # (openings are otherwise set back in the wall by their reveal depth); a door or window
        # inside an arcade stands on the arcade's back wall.
        lift = k != "pediment" and r[1] + r[3] > H + MIN_ and in_pediment(r, peds)
        dist = 0.35 * ped_d + 0.01 * m + (depth if k in ("window", "door", "shop") else 0.0)
        back = None
        if k != "arcade":
            back = next((a for a in arcades if in_pediment(r, [a[0]])), None)
            if back is not None:
                inside_arcade.setdefault(id(back), []).append((r, k))
        for p in parts[start:end]:
            p["join"] = _named(name, tag)
            if lift:
                _shift(p, place(0, -dist, 0), place(0, 0, 0))
            elif back is not None:
                _shift(p, place(0, back[1], 0), place(0, 0, 0))
    parts.extend(_arcade_recesses(arcades, inside_arcade, place, box, name, T, rot, wall_color, m))
    if f.get("depth", 0.0) > 2 * T:
        parts.extend(_volume(f, place, box, name, wall_color, m))
    parts = _categorize(parts, name, f.get("color"))
    if f.get("style") == "modern":
        _modern(parts)
    if f.get("palette"):
        apply_palette(parts, f["palette"])
    return parts


TRIM = ("cornices", "mouldings", "sills", "pillars", "ornaments", "rustication", "quoins", "pediments",
        "balconies", "windows/surrounds", "doors/surrounds")


def palette_key(cat):
    """Which palette colour a category takes, or None."""
    top, sub = cat.split("/")[0], cat.rsplit("/", 1)[-1]
    if cat == "balconies/railings" or cat == "stairs/railings":
        return "railings"
    if sub in ("frames", "bars") and top in ("windows", "doors", "shopfronts"):
        return "frames"
    if sub == "glass":
        return "glass"
    if cat in ("doors/leaves",):
        return "doors"
    if cat in TRIM:
        return "trim"
    return {"walls": "wall", "arcades": "wall", "shutters": "shutters", "spandrels": "spandrels", "roof": "roof",
            "roof/chimneys": "wall", "roof/dormers": "trim"}.get(cat)


def apply_palette(parts, pal):
    """Photo colours as object colours, by category family."""
    for p in parts:
        key = palette_key(p.get("cat", ""))
        if key in pal:
            p["color"] = pal[key]


def _arcade_recesses(arcades, inside, place, box, name, T, rot, color, m):
    """Behind each row of arcades (same sill line): a back wall at the arcade depth with holes
    for the doors and windows read inside the arches, a ceiling at the highest crown and the two
    side returns. The facade wall itself has the arches cut out."""
    rows = []
    for a in sorted(arcades, key=lambda a: (round(a[0][1], 2), a[0][0])):
        if rows and abs(rows[-1][0][0][1] - a[0][1]) <= 0.05 * m:
            rows[-1].append(a)
        else:
            rows.append([a])
    out = []
    for n, row in enumerate(rows):
        u0 = min(a[0][0] for a in row)
        u1 = max(a[0][0] + a[0][2] for a in row)
        v0 = min(a[0][1] for a in row)
        top = max(a[0][1] + a[0][3] for a in row)
        d = max(a[1] for a in row)
        if d <= T + 0.05 * m:
            continue
        holes, eps = [], 1e-3 * m
        for a in row:
            for (r, k) in inside.get(id(a), []):
                hu, hv = r[0] - u0, max(r[1] - v0, eps)
                hw, hh = r[2], min(r[3], top - v0 - eps - hv)
                if hu > eps and hu + hw < u1 - u0 - eps and hw > eps and hh > eps:
                    holes.append([hu, hv, hw, hh])
        # Overlapping holes would break the planar face: merge them, keep those still inside.
        holes = [hh for hh in _merge_rects(holes)
                 if hh[0] > eps and hh[1] > 0 and hh[0] + hh[2] < u1 - u0 - eps and hh[1] + hh[3] < top - v0 - eps]
        tag = "arcade row %d" % n
        out.append({"type": "panel", "name": _named(name, tag + " back"), "at": place(u0, d, v0), "rot": rot,
                    "size": [u1 - u0, top - v0], "t": T, "holes": holes, "color": color})
        slab = min(0.3 * m, (top - v0) / 6.0)
        out.append(box(tag + " ceiling", u0, T, top - slab, u1 - u0, d - T, slab, color))
        for su in (max(0.0, u0 - T), u1):
            out.append(box(tag + " side", su, T, v0, T, d - T, top - v0, color))
    return out


def _shift(p, a, b):
    """Moves a planned part (and its cutters) by the vector b -> a."""
    d = [a[i] - b[i] for i in range(3)]
    for q in [p] + p.get("cut", []):
        if "at" in q:
            q["at"] = [q["at"][i] + d[i] for i in range(3)]


MODERN = {"frames": "#3a3d42", "bars": "#3a3d42", "glass": "#2f3b46", "leaves": "#3a3d42"}


def _modern(parts):
    """Modern style: slim anthracite profiles and dark glass, as object colours (the shared
    Frames/Glass layers keep their colours for other buildings in the same file)."""
    for p in parts:
        sub = p.get("cat", "").rsplit("/", 1)[-1]
        if sub in MODERN and p.get("cat", "").split("/")[0] in ("windows", "doors", "shopfronts"):
            p["color"] = MODERN[sub]


SUBPART = {"frame": "frames", "glass": "glass", "bar": "bars", "leaf": "leaves",
           "surround": "surrounds", "keystone": "surrounds", "sign": "signs"}
RAILING = ("iron",)   # wrought-iron railings get their own dark layer; balustrades are stone


def _categorize(parts, name, user_color):
    """Gives every planned facade part its object and layer category. Colours then come from the
    category layers; only a colour the user set on the facade stays, on its walls."""
    for p in parts:
        words = p["name"][len(name) + 1:].split()
        head = words[0]
        if head in ("wall", "side", "back"):
            cat = "walls"
        elif head == "floor":
            cat = "floors"
        elif head == "roof":
            cat = "roof"
        else:
            cat = ELEMENT_CATEGORY[head]
            if head in ("window", "door", "shop"):
                sub = SUBPART[words[-1]]
                if head == "shop" and sub == "surrounds":
                    cat = "windows/surrounds"
                elif head != "shop" and sub == "signs":
                    cat += "/frames"
                else:
                    cat += "/" + sub
            elif head == "balcony" and words[-1] in RAILING:
                cat = "balconies/railings"
            elif head == "balcony" and words[-1] == "glass":
                cat = "balconies/glass"
        p["obj"], p["cat"] = name, cat
        if cat == "walls" and user_color:
            p["color"] = user_color
        else:
            p.pop("color", None)
    return parts


# Each face of a block: corner it starts from (in w, d) and the facade rotation that makes its
# u axis run along the outside, left to right as seen from outside, with depth pointing inward.
FACE_START = {"front": (0, 0, 0.0), "right": (1, 0, 90.0), "back": (1, 1, 180.0), "left": (0, 1, -90.0)}


def _wrap(angle):
    return ((angle + 180.0) % 360.0) - 180.0


def plan_block(b):
    W, D, H, T, m = b["w"], b["d"], b["h"], b["t"], b["per_m"]
    ax, ay, az = b["at"]
    c, s = math.cos(math.radians(b["rot"])), math.sin(math.radians(b["rot"]))
    name = b.get("name", "block")

    def world(x, y, z):
        return [ax + c * x - s * y, ay + s * x + c * y, az + z]

    parts = []
    for key in FACES:
        sx, sy, frot = FACE_START[key]
        length = W if key in ("front", "back") else D
        rot = _wrap(b["rot"] + frot)
        f = {"w": length, "h": H, "t": T, "per_m": m, "at": world(sx * W, sy * D, 0), "rot": rot,
             "els": b["faces"].get(key, []), "name": "%s %s" % (name, key), "depth": 0.0,
             "style": b.get("style", "plain")}
        if "color" in b:
            f["color"] = b["color"]
        if "palette" in b:
            f["palette"] = b["palette"]
        fparts = plan_facade(f)
        if key in ("right", "left"):
            # Front and back walls run the full width; the side walls give up their corner
            # squares so no two walls overlap.
            fc, fs = math.cos(math.radians(rot)), math.sin(math.radians(rot))
            e = 1e-3 * m
            corner = lambda u: {"type": "box", "rot": rot, "size": [T + e, T + 2 * e, H + 2 * e],
                                "at": [f["at"][0] + fc * u + fs * e, f["at"][1] + fs * u - fc * e, az - e]}
            fparts[0].setdefault("cut", []).extend([corner(-e), corner(length - T)])
        for p in fparts:
            p["obj"], p["face"] = name, key
        parts.extend(fparts)

    slab = min(0.25 * m, H / b["floors"] / 4.0)
    for k in range(1, b["floors"]):
        parts.append({"type": "box", "name": _named(name, "floor %d" % k), "rot": b["rot"],
                      "at": world(T, T, H * k / float(b["floors"]) - slab), "size": [W - 2 * T, D - 2 * T, slab],
                      "obj": name, "cat": "floors"})
    if b["roof"] in ("flat", "gable"):
        parts.append({"type": "box", "name": _named(name, "roof slab"), "rot": b["rot"], "at": world(0, 0, H),
                      "size": [W, D, 0.3 * m], "obj": name, "cat": "roof"})
    if b["roof"] == "gable":
        z = H + 0.3 * m
        if W >= D:   # ridge along w: profile across d; rot - 90 maps local x -> -d, local y -> +w
            roof = {"at": world(0, D, z), "rot": _wrap(b["rot"] - 90.0),
                    "pts": [[0, 0], [D, 0], [D / 2.0, b["roof_h"]]], "len": W}
        else:
            roof = {"at": world(0, 0, z), "rot": b["rot"],
                    "pts": [[0, 0], [W, 0], [W / 2.0, b["roof_h"]]], "len": D}
        roof.update({"type": "prism", "name": _named(name, "roof"), "obj": name, "cat": "roof"})
        parts.append(roof)
    if b["roof"] in ("hip", "mansard"):
        z, rh, e = H + 0.3 * m, b["roof_h"], 0.005 * m
        rect = lambda x0, y0, x1, y1, zz: {"z": zz, "pts": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]}

        def hip(x0, y0, x1, y1, z0, z1):
            """Four planes from a rectangle up to a ridge along its longer side."""
            w, d = x1 - x0, y1 - y0
            if w >= d:
                top = rect(x0 + d / 2.0, (y0 + y1) / 2.0 - e, max(x1 - d / 2.0, x0 + d / 2.0 + 2 * e), (y0 + y1) / 2.0 + e, z1)
            else:
                top = rect((x0 + x1) / 2.0 - e, y0 + w / 2.0, (x0 + x1) / 2.0 + e, max(y1 - w / 2.0, y0 + w / 2.0 + 2 * e), z1)
            return [rect(x0, y0, x1, y1, z0), top]

        if b["roof"] == "hip":
            tiers = [hip(0, 0, W, D, 0, rh)]
        else:   # mansard: a steep lower slope (about 74 deg) under a shallow hipped top
            h1 = 0.65 * rh
            i = min(h1 / 3.5, W / 4.0, D / 4.0)
            tiers = [[rect(0, 0, W, D, 0), rect(i, i, W - i, D - i, h1)], hip(i, i, W - i, D - i, h1, rh)]
        for n, sections in enumerate(tiers):
            parts.append({"type": "loft", "name": _named(name, "roof %d" % n), "at": world(0, 0, z), "rot": b["rot"],
                          "sections": sections, "obj": name, "cat": "roof"})
    parts.extend(_dormers(b, world, name))
    parts.extend(_chimneys(b, world, name))
    if b.get("palette"):
        apply_palette(parts, b["palette"])
    return parts


def _chimneys(b, world, name):
    """Chimney stacks on the ridge line (on the roof slab for flat roofs), evenly spaced."""
    W, D, m, n = b["w"], b["d"], b["per_m"], b.get("chimneys", 0)
    at = b.get("chimney_at")
    if at:
        n = len(at)
    if not n or b["roof"] == "none":
        return []
    z0 = b["h"] + 0.3 * m
    top = z0 + (b["roof_h"] if b["roof"] != "flat" else 0.0) + 1.0 * m
    s = 0.6 * m
    out = []
    for k in range(n):
        if at:   # positions along the front read off the photo, on the ridge line
            x, y = min(max(at[k] - s / 2.0, 0.0), W - s), D / 2.0 - s / 2.0
        elif W >= D:
            x, y = W * (k + 1) / (n + 1.0) - s / 2.0, D / 2.0 - s / 2.0
        else:
            x, y = W / 2.0 - s / 2.0, D * (k + 1) / (n + 1.0) - s / 2.0
        out.append({"type": "box", "name": _named(name, "roof chimney %d" % k), "rot": b["rot"], "at": world(x, y, z0),
                    "size": [s, s, top - z0], "obj": name, "cat": "roof/chimneys"})
        out.append({"type": "box", "name": _named(name, "roof chimney %d cap" % k), "rot": b["rot"],
                    "at": world(x - 0.08 * m, y - 0.08 * m, top), "size": [s + 0.16 * m, s + 0.16 * m, 0.1 * m],
                    "obj": name, "cat": "roof/chimneys"})
    return out


def _dormers(b, world, name):
    """Dormers on the two long roof slopes facing front and back (y = 0 and y = d): a box with a
    window and a small gable, standing on the slope a quarter of the way up. Mansards have such
    slopes on every side; gable and hip roofs only when their ridge runs along w (w >= d).
    dormer_at [[u, w], ...] (windows read above the eaves of a front photo) places them on the
    front slope where the photo has them instead of evenly."""
    W, D, m, n = b["w"], b["d"], b["per_m"], b["dormers"]
    roof = b["roof"]
    at = b.get("dormer_at")
    if (not n and not at) or roof not in ("gable", "hip", "mansard") or (roof != "mansard" and W < D):
        return []
    rh, z0 = b["roof_h"], b["h"] + 0.3 * m
    if roof == "mansard":
        h1 = 0.65 * rh
        i = min(h1 / 3.5, W / 4.0, D / 4.0)
        run, rise, margin = i, h1, i
    else:
        run, rise, margin = D / 2.0, rh, (D / 2.0 if roof == "hip" else 0.3 * m)
    if rise < 1.2 * m:
        return []
    t0, zb = 0.25 * run, z0 + 0.25 * rise
    dd = max(0.45 * run, 0.6 * m)
    dh = min(1.6 * m, 0.7 * rise)
    if at:
        # On a hip roof the front slope is still t0 in from each end at a quarter of its height.
        lo, hi = (t0 if roof == "hip" else 0.0) + 0.1 * m, W - (t0 if roof == "hip" else 0.0) - 0.1 * m
        spots = []
        for u, w in at:
            dw_ = max(w + 0.4 * m, 0.8 * m)
            x = min(max(u + w / 2.0 - dw_ / 2.0, lo), hi - dw_)
            if x >= lo - 1e-9:
                spots.append((0, x, dw_))
    else:
        dw = 1.2 * m
        usable = W - 2 * margin
        n = min(n, int(usable // (dw * 1.6)))
        if n < 1:
            return []
        spots = [(side, margin + usable * (k + 0.5) / n - dw / 2.0, dw) for side in (0, 1) for k in range(n)]
    out = []
    for j, (side, x, dw) in enumerate(spots):
        y = t0 if side == 0 else D - t0 - dd
        tag = "dormer %d" % j
        out.append({"type": "box", "name": _named(name, "roof " + tag), "rot": b["rot"],
                    "at": world(x, y, zb), "size": [dw, dd, dh], "obj": name, "cat": "roof/dormers"})
        out.append({"type": "prism", "name": _named(name, "roof " + tag + " gable"), "rot": b["rot"],
                    "at": world(x, y, zb + dh), "len": dd,
                    "pts": [[0, 0], [dw, 0], [dw / 2.0, dw * 0.45]], "obj": name, "cat": "roof/dormers"})
        gy = y - 0.02 * m if side == 0 else y + dd - 0.01 * m
        out.append({"type": "box", "name": _named(name, "roof " + tag + " glass"), "rot": b["rot"],
                    "at": world(x + 0.15 * m, gy, zb + 0.2 * m), "size": [dw - 0.3 * m, 0.03 * m, dh - 0.35 * m],
                    "obj": name, "cat": "roof/dormers/glass"})
    return out



CAPITAL_H = {"tuscan": 0.5, "doric": 0.5, "ionic": 0.45, "corinthian": 1.17}   # in lower diameters


def plan_column(c):
    """Column(s) standing on the ground at at: square plinth, moulded base (half a diameter in
    all), a shaft swelling slightly (entasis) and tapering to 5/6 of its foot, an astragal, and
    the capital of the order. Rows run along x (or y) every spacing."""
    d, H, order = c["d"], c["h"], c["order"]
    r = d / 2.0
    ax, ay, az = c["at"]
    rot = c["rot"]
    cs, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    name = c.get("name", "column")
    base_h, cap_h = 0.5 * d, CAPITAL_H[order] * d
    z0, z1 = base_h, H - cap_h          # shaft
    top_r = r * 5 / 6.0
    out = []

    def add(kind, label, x, y, **kw):
        p = {"type": kind, "name": _named(name, label), "obj": name, "cat": "pillars", "rot": rot,
             "at": [ax + cs * x - sn * y, ay + sn * x + cs * y, az + kw.pop("z", 0.0)]}
        p.update(kw)
        out.append(p)

    for i in range(c["count"]):
        x, y = (i * c["spacing"], 0.0) if c["axis"] == "x" else (0.0, i * c["spacing"])
        tag = "%d" % i
        pl = 1.35 * d
        add("box", tag + " plinth", x - pl / 2.0, y - pl / 2.0, size=[pl, pl, 0.2 * d])
        add("revolve", tag + " base", x, y, profile=[[0, 0.2 * d], [0.62 * d, 0.2 * d], [0.62 * d, 0.27 * d],
                                                       [0.56 * d, 0.34 * d], [0.53 * d, 0.40 * d],
                                                       [r, 0.45 * d], [r, base_h], [0, base_h]])
        L = z1 - z0
        add("revolve", tag + " shaft", x, y, profile=[[0, z0], [r, z0], [r, z0 + L / 3.0], [r * 0.95, z0 + 2 * L / 3.0],
                                                        [top_r, z1 - 0.06 * d], [top_r * 1.08, z1 - 0.03 * d],
                                                        [top_r, z1], [0, z1]])
        if order in ("tuscan", "doric"):
            add("revolve", tag + " capital", x, y, profile=[[0, z1], [top_r, z1], [top_r, z1 + 0.12 * d],
                                                              [0.58 * d, z1 + 0.3 * d], [0.58 * d, z1 + 0.33 * d],
                                                              [0, z1 + 0.33 * d]])
            ab = 1.2 * d
            add("box", tag + " capital", x - ab / 2.0, y - ab / 2.0, z=z1 + 0.33 * d, size=[ab, ab, H - z1 - 0.33 * d])
        elif order == "ionic":
            add("revolve", tag + " capital", x, y, profile=[[0, z1], [top_r, z1], [0.55 * d, z1 + 0.2 * d],
                                                              [0, z1 + 0.2 * d]])
            ab = 1.15 * d
            add("box", tag + " capital", x - ab / 2.0, y - 0.55 * d, z=z1 + 0.32 * d, size=[ab, 1.1 * d, H - z1 - 0.32 * d])
            for side in (-1, 1):   # the two volutes, rolled cushions seen from the front
                add("cyl", tag + " volute", x + side * 0.5 * d, y - 0.55 * d, z=z1 + 0.2 * d,
                    tilt=[-90.0, 0.0], r=0.17 * d, h=1.1 * d)
        else:   # corinthian: a bell of leaves flaring to a concave abacus
            add("revolve", tag + " capital", x, y, profile=[[0, z1], [top_r, z1], [top_r * 1.05, z1 + 0.4 * d],
                                                              [0.55 * d, z1 + 0.8 * d], [0.66 * d, z1 + 1.0 * d],
                                                              [0, z1 + 1.0 * d]])
            ab = 1.3 * d
            add("box", tag + " capital", x - ab / 2.0, y - ab / 2.0, z=z1 + 1.0 * d, size=[ab, ab, H - z1 - 1.0 * d])
    return out


def plan_stair(s):
    """Stair as primitives: solid steps, a core column for spirals, posts and handrails."""
    m, n, H = s["per_m"], s["n"], s["h"]
    riser = H / n
    ax, ay, az = s["at"]
    rot = s["rot"]
    c, sn = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    name = s.get("name", "stair")

    def world(x, y, z):
        return [ax + c * x - sn * y, ay + sn * x + c * y, az + z]

    def part(kind, label, cat, **kw):
        p = {"type": kind, "name": _named(name, label), "obj": name, "cat": cat}
        p.update(kw)
        return p

    rail_h, post_r, hand_r = 0.9 * m, 0.02 * m, 0.025 * m
    out = []
    if s["kind"] == "straight":
        W, T = s["w"], s["tread"]
        for k in range(n):   # each step a solid block down to the floor: a closed, buildable stair
            out.append(part("box", "step %d" % k, "stairs/steps", at=world(0, k * T, 0), rot=rot,
                            size=[W, T, (k + 1) * riser]))
        sides = {"both": (0, 1), "left": (0,), "right": (1,), "outer": (1,), "none": ()}[s["rail"]]
        for side in sides:
            x = 0.05 * m if side == 0 else W - 0.05 * m
            for k in range(0, n, 2):
                out.append(part("cyl", "post %d" % k, "stairs/railings", at=world(x, (k + 0.5) * T, (k + 1) * riser),
                                rot=rot, r=post_r, h=rail_h))
            # handrail parallel to the pitch line, relative to the first post's foot
            y0, z0 = 0.5 * T, riser + rail_h
            y1, z1 = (n - 0.5) * T, n * riser + rail_h
            out.append(part("pipe", "handrail %d" % side, "stairs/railings", at=world(x, y0, z0), rot=rot,
                            path=[[0, 0, 0], [0, y1 - y0, z1 - z0]], r=hand_r))
        return out

    R, r0, a = s["r"], s["core"], s["step"]
    out.append(part("cyl", "core", "stairs", at=world(0, 0, 0), rot=rot, r=r0, h=H + rail_h))
    seg = 4
    for k in range(n):
        # wedge from the core to r spanning one step angle, as a flat polygon extruded one riser
        pts = [[r0 * 0.5, 0]]
        for j in range(seg + 1):
            t = math.radians(a * j / seg)
            pts.append([R * math.cos(t), R * math.sin(t)])
        pts.append([r0 * 0.5 * math.cos(math.radians(a)), r0 * 0.5 * math.sin(math.radians(a))])
        out.append(part("extrude", "step %d" % k, "stairs/steps", at=world(0, 0, k * riser),
                        rot=_wrap(rot + k * a), pts=pts, h=riser * 0.35 if k else riser))
    if s["rail"] != "none":
        rr = R - 0.05 * m
        path = []
        for k in range(n + 1):
            t = math.radians(rot + k * a)   # path is relative to at but not rotated with the part
            path.append([rr * math.cos(t), rr * math.sin(t), k * riser + rail_h])
        for k in range(n):
            t = math.radians(rot + (k + 0.5) * a)
            out.append(part("cyl", "post %d" % k, "stairs/railings", rot=0.0, r=post_r, h=rail_h,
                            at=[ax + rr * math.cos(t), ay + rr * math.sin(t), az + (k + 1) * riser]))
        out.append(part("pipe", "handrail", "stairs/railings", at=[ax, ay, az], rot=0.0, path=path, r=hand_r))
    return out


def _volume(f, place, box, name, color, m):
    """Side walls, back wall, floor slabs and roof behind a facade of the given depth."""
    W, H, T, D, rot = f["w"], f["h"], f["t"], f["depth"], f["rot"]
    out = [box("side left", 0, T, 0, T, D - T, H, color),
           box("side right", W - T, T, 0, T, D - T, H, color),
           box("back", T, D - T, 0, W - 2 * T, T, H, color)]
    floors = f.get("floors", 1)
    for k in range(1, floors):
        slab = min(0.25 * m, H / floors / 4.0)
        out.append(box("floor %d" % k, T, T, H * k / float(floors) - slab, W - 2 * T, D - 2 * T, slab, "#bdb6a8"))
    roof = f.get("roof", "flat")
    if roof in ("flat", "gable"):
        out.append(box("roof slab", 0, 0, H, W, D, 0.3 * m, "#8a7f72"))
    if roof == "gable":
        # Ridge parallel to the facade: rot + 90 turns the part's local x into the facade depth
        # and its local y into -u, so the prism runs from u = W back to u = 0.
        r90 = rot + 90.0 if rot + 90.0 <= 360 else rot - 270.0
        out.append({"type": "prism", "name": _named(name, "roof"), "at": place(W, 0, H + 0.3 * m),
                    "rot": r90, "len": W, "pts": [[0, 0], [D, 0], [D / 2.0, f.get("roof_h", 3.0)]],
                    "color": "#8a4b3a"})
    return out
