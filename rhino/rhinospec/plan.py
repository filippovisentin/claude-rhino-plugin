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
        if p["name"].endswith("roof slab") and b["roof"] == "flat":
            p["cat"] = "roof/flat"
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
    "spandrel": "#3b4048", "pediment": "#d6cdbb", "arcade": "#e1dacb", "clad": "#8f8a82", "pipe": "#8c8f93",
    "finial": "#d6cdbb",
}
# Default depth per class: recess for openings, projection for everything else.
DEPTH = {"window": 0.12, "door": 0.15, "shop": 0.10, "cornice": 0.30, "molding": 0.06,
         "pillar": 0.12, "sill": 0.06, "blind": 0.04, "deco": 0.04, "balcony": 1.0, "rustic": 0.03, "quoin": 0.04,
         "spandrel": 0.03, "pediment": 0.5, "arcade": 3.0,
         "clad": 0.03, "pipe": 0.04, "finial": 0.0}


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
    """[u, v, w, h] of every pediment resting on the wall: they rise above the eaves, so they are
    not clipped there. One whose base is above the wall's top edge would float; it is clipped
    (and so dropped and reported) like any other element."""
    return [[u, v, w, h] for el, u, v, w, h in _expanded(f) if el["k"] == "pediment" and _rests(f, u, v, w)]


# What a pediment's box keeps above the eaves: itself, an oculus or window in the tympanum, reliefs
# and mouldings. A portico, door or balcony read there would hang in the air.
IN_PEDIMENT = ("pediment", "window", "deco", "molding", "cornice")

# Elements that project from the wall: their ends may overhang the edge of what carries them (a
# cornice crowning a pavilion, a pediment whose sides fall on the outline's risers).
OVERHANG = ("molding", "cornice", "pediment", "deco", "sill", "finial")


def _core(f, k, u, w):
    """The stretch u0..u1 of an element's width that must lie under the wall's top edge."""
    u0, u1 = max(u, 0.0), min(u + w, f.get("w", u + w))
    if k in OVERHANG and u1 > u0:
        cut = min(0.3 * f.get("per_m", 1.0), 0.1 * (u1 - u0))
        u0, u1 = u0 + cut, u1 - cut
    return u0, u1


def _rests(f, u, v, w, k="pediment"):
    """Whether an element based at v over u..u + w stands on the wall (at or below its top edge)."""
    if "h" not in f:          # a partial facade (only its elements): no top edge to test
        return True
    return v <= outline_height(f, *_core(f, k, u, w)) + EPS


def in_pediment(r, peds, tol=1e-6):
    """The pediment box holding r (an oculus, a relief in the tympanum), or None."""
    u, v, w, h = r
    for pu, pv, pw, ph in peds:
        if u >= pu - tol and u + w <= pu + pw + tol and v >= pv - tol and v + h <= pv + ph + tol:
            return [pu, pv, pw, ph]
    return None


def top_outline(f):
    """The wall's top edge, left to right: the eaves line, or the eaves corners joined through
    the facade's top points (a gable, a stepped gable, a raised parapet)."""
    pts = [[0.0, f["h"]]] + [list(q) for q in f.get("top", [])] + [[f["w"], f["h"]]]
    out = []
    for q in pts:
        if not out or abs(q[0] - out[-1][0]) > EPS or abs(q[1] - out[-1][1]) > EPS:
            out.append(q)
    return out


def top_polygons(f):
    """Outlines [[u, v], ...] of the wall above the eaves: one per run of the top edge that leaves
    the eaves line (a single gable, or two gables with a valley at the eaves between them)."""
    line, H = top_outline(f), f["h"]
    polys, run = [], []
    for q in line:
        if q[1] <= H + EPS:
            if len(run) > 0:
                run.append(q)
                polys.append(_ccw(run))
            run = [q]
        else:
            run.append(q)
    return [pp for pp in polys if len(pp) >= 3 and abs(polygon_area(pp)) > EPS]


def outline_height(f, u0, u1):
    """Lowest point of the wall's top edge over u0..u1: an element there stays inside the wall."""
    if not f.get("top"):
        return f["h"]
    vs = []
    line = top_outline(f)
    for a, b in zip(line, line[1:]):
        if abs(b[0] - a[0]) <= EPS:            # a step riser: only one strictly inside counts
            if u0 + EPS < a[0] < u1 - EPS:
                vs += [a[1], b[1]]
            continue
        lo, hi = max(a[0], u0), min(b[0], u1)
        if lo <= hi + EPS:
            for x in (lo, min(max(hi, lo), b[0])):
                vs.append(a[1] + (b[1] - a[1]) * (x - a[0]) / (b[0] - a[0]))
    return min(vs) if vs else f["h"]


def _clip(f, el, u, v, w, h, peds):
    top = outline_height(f, *_core(f, el["k"], u, w))
    if (el["k"] in IN_PEDIMENT and in_pediment([u, v, w, h], peds)) or (el["k"] == "finial" and _rests(f, u, v, w, "finial")):
        top = max(top, v + h)                # a resting pediment holds its own box; finials stand up
    cu0, cv0 = max(u, 0.0), max(v, 0.0)
    cu1, cv1 = min(u + w, f["w"]), min(v + h, top)
    return [cu0, cv0, cu1 - cu0, cv1 - cv0]


def clipped_elements(f):
    """How many elements are built but cut short by the facade outline (by more than 5 cm)."""
    peds = pediment_boxes(f)
    m = f.get("per_m", 1.0)
    n = 0
    for el, u, v, w, h in _expanded(f):
        r = _clip(f, el, u, v, w, h, peds)
        if r[2] >= MIN_EL * m and r[3] >= MIN_EL * m and (w - r[2] > 0.05 * m or h - r[3] > 0.05 * m):
            n += 1
    return n


def facade_elements(f):
    """Expands grids and clips every element to the facade: its sides, the ground and the top
    edge (pediments, and what sits inside them, may rise above it). Returns [(k, [u, v, w, h], el)]."""
    out = []
    peds = pediment_boxes(f)
    min_el = MIN_EL * f.get("per_m", 1.0)
    for el, u, v, w, h in _expanded(f):
        cu0, cv0, cw, ch = _clip(f, el, u, v, w, h, peds)
        if cw >= min_el and ch >= min_el:
            out.append((el["k"], [cu0, cv0, cw, ch], el))
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


def _band(flat, label, outer, inner, d0, depth, color, open_foot=False):
    """A band between two outlines (a surround, a ring, a frame) as one solid: the outer outline
    extruded, with the inner one cut through it. Segments joined into a ring leave open,
    non-manifold unions in Rhino. open_foot: the inner outline's two foot corners go below the
    outer one, so the band has no bottom (a door surround)."""
    e = 0.001 + 0.05 * depth
    inner = [list(q) for q in inner]
    if open_foot:
        low = min(q[1] for q in outer) - e
        for q in inner[:2]:                  # opening_outline starts with the two foot corners
            q[1] = low
    band = flat(label, outer, d0, depth, color)
    band["cut"] = [flat(label, inner, d0 - e, depth + 2 * e, color)]
    return band


def _surround(box, flat, tag, u, v, w, h, sur, k, shape, m, foot=None):
    """Moulded band around an opening, proud of the wall. On arches the band follows the curve
    (an archivolt, built from short segments) and carries a keystone at the crown; round openings
    get a ring with a keystone."""
    proj = min(0.06 * m, sur / 2.0)
    if shape == "round":
        out = [_band(flat, tag + " surround", opening_outline(u, v, w, h, "round"),
                     opening_outline(u + sur, v + sur, w - 2 * sur, h - 2 * sur, "round"), -proj, proj, COLORS["sill"])]
        kw = min(0.25 * m, w / 4.0)
        out.append(box(tag + " keystone", u + (w - kw) / 2.0, -proj * 1.6, v + h - sur * 1.6, kw, proj * 1.6,
                       sur * 1.6, COLORS["sill"]))
        return out
    rise = arc_rise(shape, w, h) if shape in ("arch", "seg") else 0.0
    # The opening inside the band: doors (and windows down to the foot) have no band under them.
    foot = (k == "door") if foot is None else foot
    ib = [u + sur, v, w - 2 * sur, h - sur] if foot else [u + sur, v + sur, w - 2 * sur, h - 2 * sur]
    if rise and (ib[2] <= 0 or ib[3] <= 0 or arc_rise(shape, ib[2], ib[3]) <= 0 or ib[3] <= arc_rise(shape, ib[2], ib[3])):
        rise = 0.0   # an opening too small for a curved band: straight jambs and head
    sh = shape if rise else "rect"
    out = [_band(flat, tag + " surround", opening_outline(u, v, w, h, sh), opening_outline(ib[0], ib[1], ib[2], ib[3], sh),
                 -proj, proj, COLORS["sill"], open_foot=foot)]
    if shape in ("arch", "seg"):
        kw = min(0.25 * m, w / 4.0)
        out.append(box(tag + " keystone", u + (w - kw) / 2.0, -proj * 1.6, v + h - sur * 1.6, kw, proj * 1.6,
                       sur * 1.6 + 0.04 * m, COLORS["sill"]))
    return out


def _console_drop(cu, cw, v, ch, openings):
    """How far a console under a slab at v can hang over cu..cu + cw: down to ch, but never over an
    opening (or its surround) that reaches up under the slab, nor in front of one it stands across."""
    drop = ch
    for ou, ov, ow, oh in openings:
        if ou < cu + cw - EPS and ou + ow > cu + EPS and ov < v - EPS:
            drop = min(drop, v - min(ov + oh, v))
    return drop


def _balcony(box, along, tag, u, v, w, h, depth, rail, classic, m, openings=()):
    """Slab, consoles underneath (classic) and a railing: balustrade, iron bars, solid parapet, or
    glass panes between slim metal posts. Consoles shorten above an opening below (or go when less
    than 8 cm is left), so they never hang in front of a window head."""
    slab_t = min(0.15 * m, h)
    out = [box(tag + " slab", u, -depth, v, w, depth, slab_t, COLORS["balcony"])]
    if classic:
        n = max(2, int(round(w / (0.9 * m))) + 1)
        cw, ch = min(0.22 * m, w / (2.0 * n)), min(0.6 * m, depth * 0.8)
        for i in range(n):
            cu = u + 0.1 * m + (w - 0.2 * m - cw) * i / float(n - 1)
            drop = _console_drop(cu, cw, v, ch, openings)
            if drop < 0.08 * m:
                continue
            if drop > 0.15 * m:
                pts = [[0, v - drop], [0, v], [-0.85 * depth, v], [-0.85 * depth, v - 0.12 * m], [-0.2 * m, v - drop]]
            else:   # a short bracket: tapered block
                pts = [[0, v - drop], [0, v], [-0.85 * depth, v], [-0.5 * depth, v - drop]]
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


def _garage(box, tag, u, v, w, h, r, m):
    """Sectional garage door: one leaf with a shallow groove between panels about 0.5 m high."""
    d0 = r + 0.03 * m
    out = [box(tag + " leaf", u, d0, v, w, 0.05 * m, h, COLORS["door"])]
    n = max(2, int(round(h / (0.5 * m))))
    g = min(0.025 * m, h / (4.0 * n))
    for i in range(1, n):
        out.append(box(tag + " leaf", u, d0 - 0.015 * m, v + h * i / float(n) - g / 2.0, w, 0.015 * m, g,
                       COLORS["door"]))
    return out


def _cladding(place, rot, name, tag, u, v, w, h, depth, openings, T, m):
    """A zone of another material (stone base, timber, brick band) laid on the wall face, with the
    openings that fall in it cut through."""
    eps = 1e-3 * m
    holes, cuts = [], []
    for r, sh in openings:
        if r[0] <= u + eps and r[0] + r[2] >= u + w - eps and r[1] <= v + eps and r[1] + r[3] >= v + h - eps:
            return None   # the zone lies inside an opening: nothing of it is seen
        if r[0] >= u + w or r[0] + r[2] <= u or r[1] >= v + h or r[1] + r[3] <= v:
            continue
        if r[0] > u + eps and r[0] + r[2] < u + w - eps and r[1] > v + eps and r[1] + r[3] < v + h - eps:
            hole = [r[0] - u, r[1] - v, r[2], r[3]]
            holes.append(hole + [OPENING_SHAPES.index(sh)] if sh != "rect" else hole)
        else:
            cuts.append({"type": "prism", "at": place(0, -T, 0), "rot": rot, "len": 3 * T,
                         "pts": opening_outline(r[0] - eps, r[1] - eps, r[2] + 2 * eps, r[3] + 2 * eps, sh)})
    part = {"type": "panel", "name": _named(name, tag), "at": place(u, -depth, v), "rot": rot,
            "size": [w, h], "t": depth, "holes": holes, "color": COLORS["clad"]}
    if cuts:
        part["cut"] = cuts
    return part


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


# Urn outline: (radius, height) as fractions of the body's largest radius and height.
URN = ((0, 0), (0.55, 0), (0.4, 0.12), (1.0, 0.5), (0.85, 0.72), (0.45, 0.8), (0.6, 0.86), (0.25, 0.93), (0, 1.0))


def _finial(f, place, box, tag, u, v, w, h, shape, rot, name, m):
    """A finial or urn read in the box: a square pedestal (its lower third) and a body of revolution
    on it. On the wall's top edge (a parapet, a gable) it stands over the wall thickness; lower down
    (on a cornice, a balustrade) it stands in front of the wall, against it."""
    T = f["t"]
    on_top = v >= outline_height(f, max(u, 0.0), min(u + w, f["w"])) - 1e-3 * m
    d0, dep = ((0.0, T) if T <= w else ((T - w) / 2.0, w)) if on_top else (-w, w)
    ph = h / 3.0
    bh = h - ph
    rmax = 0.45 * min(w, dep)
    cu, cd, z = u + w / 2.0, d0 + dep / 2.0, v + ph
    color = COLORS["finial"]
    out = [box(tag, u, d0, v, w, dep, ph, color)]
    body = _named(name, tag + " body")
    if shape == "spire":
        out.append({"type": "cone", "name": body, "at": place(cu, cd, z), "rot": rot, "r": rmax, "r2": 0.0, "h": bh,
                    "color": color})
    elif shape == "ball":
        rb = min(rmax, bh / 2.0)
        neck = bh - 2 * rb
        if neck > 1e-3 * m:
            out.append({"type": "cyl", "name": body, "at": place(cu, cd, z), "rot": rot, "r": rb * 0.4,
                        "h": neck + 0.1 * rb, "color": color})
        out.append({"type": "sphere", "name": body, "at": place(cu, cd, v + h - rb), "rot": rot, "r": rb,
                    "color": color})
    else:
        out.append({"type": "revolve", "name": body, "at": place(cu, cd, z), "rot": rot,
                    "profile": [[rmax * a, bh * b] for a, b in URN], "color": color})
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
        # No room under the opening (a door, a window down to the foot of the facade): the band
        # stops at the foot instead of going. Above, the room is up to the wall's top edge.
        foot = k == "door" or (k == "window" and el.get("shape") != "round" and v < sur)
        if sur > 0:
            above = max(H, outline_height(f, max(u, 0.0), min(u + w, W))) - v - h
            room = [u, W - u - w, above] + ([] if foot else [v])
            sur = min([sur] + room)
        if sur > MIN_:
            inner = r
            r = [u - sur, v if foot else v - sur, w + 2 * sur, h + sur if foot else h + 2 * sur]
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

    if f.get("top"):
        # The wall above the eaves (gable, stepped gable, raised parapet) with every opening that
        # reaches into it cut out, and a coping along its top edge.
        line = top_outline(f)
        high = [(r, sh) for r, sh in openings if r[1] + r[3] > H + eps]
        for poly in top_polygons(f):
            gable = {"type": "prism", "name": _named(name, "wall top"), "at": place(0, 0, 0), "rot": rot, "len": T,
                     "pts": poly, "color": wall_color}
            lo, hi = min(q[0] for q in poly), max(q[0] for q in poly)
            mine = [(r, sh) for r, sh in high if r[0] < hi and r[0] + r[2] > lo]
            if mine:
                gable["cut"] = [{"type": "prism", "at": place(0, -T, 0), "rot": rot, "len": 3 * T,
                                 "pts": opening_outline(r[0] - eps, r[1] - eps, r[2] + 2 * eps, r[3] + 2 * eps, sh)}
                                for r, sh in mine]
            parts.append(gable)
        ct, cd = (0.15 * m, 0.08 * m) if classic else (0.08 * m, 0.04 * m)
        for a, b in zip(line, line[1:]):
            if b[0] - a[0] <= EPS:
                continue   # a step riser: the treads' copings cover its corners
            a0, b0 = list(a), list(b)
            if abs(b[1] - a[1]) <= EPS:
                a0[0], b0[0] = max(a[0] - cd, -cd), min(b[0] + cd, W + cd)
            parts.append(flat("coping", [a0, b0, [b0[0], b0[1] + ct], [a0[0], a0[1] + ct]], -cd, T + 2 * cd,
                              COLORS["cornice"]))

    opening_boxes = [r for k, r, el, sur, inner in els if k in ("window", "door", "shop")]
    marks = []   # (first part index, tag) per element: its parts are joined into one solid per layer
    for n, (k, (u, v, w, h), el, sur, inner) in enumerate(els):
        tag = "%s %d" % (k, n)
        depth = el.get("d", DEPTH[k] * m)
        marks.append((len(parts), tag, k, [u, v, w, h], depth, el.get("color")))
        shape = el.get("shape")
        if k in ("window", "door", "shop"):
            if sur > 0:
                parts.extend(_surround(box, flat, tag, u, v, w, h, sur, k, shape, m, foot=abs(inner[1] - v) < EPS))
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
            parts.append(_band(flat, tag + " frame", opening_outline(u, v, w, h, "round"), ring_in, r,
                               min(0.08 * m, T - r), COLORS["frame"]))
            parts.append(flat(tag + " glass", ring_in, r + 0.03 * m, GLASS_, COLORS["glass"]))
        elif k in ("window", "door", "shop") and shape in ("arch", "seg"):
            r = min(depth, T - GLASS_ * 2)
            fr = min(FRAME_, w / 4.0, h / 4.0)
            iu, iv, iw, ih = u + fr, v + fr, w - 2 * fr, h - 2 * fr
            if iw < MIN_ or ih < MIN_:
                continue
            if k == "door" and el.get("leaf", "glass" if modern else "panel") != "glass":
                parts.extend(_door(box, flat, tag, iu, iv, iw, ih, r, shape, m))
                continue
            if k == "window":   # the frame follows the arch, like the rectangular windows' frames
                parts.append(_band(flat, tag + " frame", opening_outline(u, v, w, h, shape),
                                   opening_outline(iu, iv, iw, ih, shape), r, min(0.08 * m, T - r), COLORS["frame"]))
            parts.append({"type": "prism", "name": _named(name, tag + " glass"),
                          "at": place(0, r + 0.03 * m, 0), "rot": rot, "len": GLASS_,
                          "pts": opening_outline(iu, iv, iw, ih, shape), "color": COLORS["glass"]})
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
            leaf_kind = el.get("leaf", "glass" if modern else "panel")   # modern doors: glass in a slim frame
            if k == "door" and leaf_kind == "panel":
                parts.extend(_door(box, flat, tag, iu, iv, iw, ih, r, "rect", m))
                continue
            if k == "door" and leaf_kind == "garage":
                parts.extend(_garage(box, tag, iu, iv, iw, ih, r, m))
                continue
            glazed = True
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
                                  classic, m, opening_boxes))
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
                # The read box is the widest outline, the capital: base and shaft are thinner.
                base_h, cap_h = min(0.35 * m, h * 0.08), min(0.4 * m, h * 0.1)
                parts.append(cyl(tag + " base", rr * 1.18 / 1.22, v, base_h))
                parts.append(cyl(tag, rr / 1.22, v + base_h, h - base_h - cap_h))
                parts.append(cyl(tag + " capital", rr, v + h - cap_h, cap_h))
            else:
                parts.append(cyl(tag, rr, v, h))
        elif k == "pillar" and classic and h >= 1.5 * m:
            base_h, cap_h, lip = min(0.35 * m, h * 0.1), min(0.45 * m, h * 0.12), min(0.06 * m, w / 4.0)
            # The read box is the widest outline (base and capital); the shaft is set in by the lip.
            parts.append(box(tag + " base", u, -depth - lip, v, w, depth + lip, base_h, COLORS[k]))
            parts.append(box(tag, u + lip, -depth, v + base_h, w - 2 * lip, depth, h - base_h - cap_h, COLORS[k]))
            parts.append(along(tag + " capital", u, w, _profile("string", v + h - cap_h, cap_h, depth + lip),
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
        elif k == "clad":
            zone = _cladding(place, rot, name, tag, u, v, w, h, depth, openings, T, m)
            if zone is not None:
                parts.append(zone)
        elif k == "finial":
            parts.extend(_finial(f, place, box, tag, u, v, w, h, shape or "urn", rot, name, m))
        elif k == "pipe":
            # Downpipe (or a gutter when wider than tall), standing off the wall by d.
            # Brackets about every 2 m tie it to the wall.
            bt = 0.03 * m
            if h >= w:
                rr = min(w / 2.0, 0.06 * m)
                parts.append({"type": "cyl", "name": _named(name, tag), "at": place(u + w / 2.0, -(depth + rr), v),
                              "rot": rot, "r": rr, "h": h, "color": COLORS[k]})
                n_b = max(2, int(h // (2.0 * m)) + 1)
                for i in range(n_b):
                    z = v + bt + (h - 3 * bt) * i / float(n_b - 1)
                    parts.append(box(tag + " bracket", u + w / 2.0 - rr / 2.0, -(depth + rr), z, rr, depth + rr, bt,
                                     COLORS[k]))
            else:
                t = min(h, 0.12 * m)
                parts.append(box(tag, u, -(depth + t), v + h - t, w, t, t, COLORS[k]))
                n_b = max(2, int(w // (2.0 * m)) + 1)
                for i in range(n_b):
                    x = u + (w - bt) * i / float(n_b - 1)
                    parts.append(box(tag + " bracket", x, -depth, v + h - t, bt, depth, t, COLORS[k]))
        else:
            parts.append(box(tag, u, -depth, v, w, depth, h, COLORS[k]))

    ends = [mk[0] for mk in marks[1:]] + [len(parts)]
    peds = pediment_boxes(f)
    ped_d = max([el.get("d", DEPTH["pediment"] * m) for k, r, el, sur, inner in els if k == "pediment"] or [0.0])
    arcades = [(r, el.get("d", DEPTH["arcade"] * m), el.get("shape", "rect")) for k, r, el, sur, inner in els
               if k == "arcade"]
    inside_arcade = {}
    for (start, tag, k, r, depth, own), end in zip(marks, ends):
        # An oculus or a relief inside a pediment stands on its tympanum, in front of the wall line
        # (openings are otherwise set back in the wall by their reveal depth); a door or window
        # inside an arcade stands on the arcade's back wall.
        lift = k != "pediment" and r[1] + r[3] > H + MIN_ and in_pediment(r, peds)
        # Openings sit back in the wall by their recess, capped by its thickness as they were built.
        recess = min(depth, T - GLASS_ * 2) if k in ("window", "door", "shop") else 0.0
        dist = 0.35 * ped_d + 0.01 * m + recess
        back = None
        if k != "arcade":
            back = next((a for a in arcades if in_pediment(r, [a[0]])), None)
            if back is not None:
                inside_arcade.setdefault(id(back), []).append((r, k))
        for p in parts[start:end]:
            p["join"] = _named(name, tag)
            if own:
                p["own_color"] = own
            if lift:
                _shift(p, place(0, -dist, 0), place(0, 0, 0))
            elif back is not None:
                _shift(p, place(0, back[1], 0), place(0, 0, 0))
    parts.extend(_arcade_recesses(arcades, inside_arcade, place, box, name, T, rot, wall_color, m))
    if f.get("depth", 0.0) > 2 * T:
        parts.extend(_volume(f, place, box, name, wall_color, m))
    parts = _categorize(parts, name, f.get("color"))
    if f.get("roof", "flat") == "flat":
        for p in parts:   # a flat roof is not a tiled one: its own layer and colour
            if p["name"].endswith("roof slab"):
                p["cat"] = "roof/flat"
    if f.get("style") == "modern":
        _modern(parts)
    if f.get("palette"):
        apply_palette(parts, f["palette"])
    for p in parts:   # an element's own colour wins over style and palette (its glass stays glass)
        own = p.pop("own_color", None)
        if own and not p.get("cat", "").endswith("/glass"):
            p["color"] = own
    return parts


TRIM = ("cornices", "mouldings", "sills", "pillars", "ornaments", "rustication", "quoins", "pediments",
        "finials", "balconies", "windows/surrounds", "doors/surrounds")


def palette_key(cat):
    """Which palette colour a category takes, or None."""
    top, sub = cat.split("/")[0], cat.rsplit("/", 1)[-1]
    if cat in ("balconies/railings", "balconies/glass", "stairs/railings"):   # a glass parapet is the railing
        return "railings"
    if sub in ("frames", "bars") and top in ("windows", "doors", "shopfronts"):
        return "frames"
    if sub == "glass":
        return "glass"
    if cat in ("doors/leaves",):
        return "doors"
    if cat in TRIM:
        return "trim"
    return {"walls": "wall", "arcades": "wall", "shutters": "shutters", "spandrels": "spandrels", "roof": "roof", "cladding": "clad",
            "roof/chimneys": "wall", "roof/dormers": "trim", "roof/flat": "roof"}.get(cat)


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
        elif head == "coping":
            cat = "cornices"
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


def _openings_z(f):
    """Height ranges (v0, v1) of the openings (windows, doors, shop fronts, arcades) of a facade."""
    return [(v, v + h) for k, (u, v, w, h), el in facade_elements(f) if k in ("window", "door", "shop", "arcade")]


def _face_place(f):
    """Facade coordinates (u along, d into the building, v up) -> world, for facade f."""
    c, s = math.cos(math.radians(f["rot"])), math.sin(math.radians(f["rot"]))
    ax, ay, az = f["at"]
    return lambda u, d, v: [ax + c * u - s * d, ay + s * u + c * d, az + v]


def _slab_voids(f, place, z0, z1, m):
    """Cutters for a floor slab z0..z1 behind the openings of facade f it could not avoid (a
    double-height shop or portico): the slab stops 1.5 m behind the wall there, so no floor shows
    through the glass."""
    e, deep = 1e-3 * m, f["t"] + 1.5 * m
    return [{"type": "box", "rot": f["rot"], "at": place(u - e, -e, z0 - e), "size": [w + 2 * e, deep + e, z1 - z0 + 2 * e]}
            for k, (u, v, w, h), el in facade_elements(f)
            if k in ("window", "door", "shop", "arcade") and v < z1 - EPS and v + h > z0 + EPS]


def _slab_tops(H, floors, slab, busy):
    """Top of each intermediate floor slab: its storey height H * k / floors when the slab is clear
    of every opening there, else the nearest height within half a storey whose slab is (a slab
    seen through the glass reads as a floor in the wrong place). Kept in order; left as is when
    nothing is free (a full-height curtain wall)."""
    spans = sorted((a, b) for a, b in busy if b > a)
    merged = []
    for a, b in spans:
        if merged and a <= merged[-1][1] + EPS:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps, z = [], 0.0
    for a, b in merged:
        gaps.append((z, a))
        z = max(z, b)
    gaps.append((z, H))
    out, last = [], 0.0
    for k in range(1, floors):
        want = H * k / float(floors)
        best = None
        for g0, g1 in gaps:
            lo, hi = max(g0, last) + slab, min(g1, H - slab)
            if hi < lo - EPS:
                continue
            t = min(max(want, lo), hi)
            if abs(t - want) <= H / float(floors) / 2.0 + EPS and (best is None or abs(t - want) < abs(best - want)):
                best = t
        t = want if best is None else best
        out.append(t)
        last = t
    return out


def plan_block(b):
    W, D, H, T, m = b["w"], b["d"], b["h"], b["t"], b["per_m"]
    ax, ay, az = b["at"]
    c, s = math.cos(math.radians(b["rot"])), math.sin(math.radians(b["rot"]))
    name = b.get("name", "block")

    def world(x, y, z):
        return [ax + c * x - s * y, ay + s * x + c * y, az + z]

    parts, busy, faces = [], [], []
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
        busy.extend(_openings_z(f))
        faces.append(f)

    slab = min(0.25 * m, H / b["floors"] / 4.0)
    for k, top in enumerate(_slab_tops(H, b["floors"], slab, busy), 1):
        floor = {"type": "box", "name": _named(name, "floor %d" % k), "rot": b["rot"],
                 "at": world(T, T, top - slab), "size": [W - 2 * T, D - 2 * T, slab], "obj": name, "cat": "floors"}
        voids = [c for f in faces for c in _slab_voids(f, _face_place(f), top - slab, top, m)]
        if voids:
            floor["cut"] = voids
        parts.append(floor)
    if b["roof"] != "none":   # every roof below starts on top of this slab
        parts.append({"type": "box", "name": _named(name, "roof slab"), "rot": b["rot"], "at": world(0, 0, H),
                      "size": [W, D, 0.3 * m], "obj": name, "cat": "roof/flat" if b["roof"] == "flat" else "roof"})
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
    top = f.get("top")
    if top:   # the back wall repeats the outline above the eaves
        for poly in top_polygons(f):
            out.append({"type": "prism", "name": _named(name, "back top"), "at": place(0, D - T, 0), "rot": rot,
                        "len": T, "pts": poly, "color": color})
    floors = f.get("floors", 1)
    slab = min(0.25 * m, H / max(floors, 1) / 4.0)
    for k, z in enumerate(_slab_tops(H, floors, slab, _openings_z(f)), 1):
        floor = box("floor %d" % k, T, T, z - slab, W - 2 * T, D - 2 * T, slab, "#bdb6a8")
        voids = _slab_voids(f, place, z - slab, z, m)
        if voids:
            floor["cut"] = voids
        out.append(floor)
    roof = f.get("roof", "flat")
    if roof in ("flat", "gable"):
        out.append(box("roof slab", 0, 0, H, W, D, 0.3 * m, "#8a7f72"))
    if roof == "gable" and top:
        # Gable end to the street: the ridge runs back from the facade, its pitch kept under the
        # outline (a stepped gable's steps stand above the roof, as built). Two gables with a
        # valley between them get a roof each.
        polys = top_polygons(f)
        for poly in polys:
            lo, hi = (0.0, W) if len(polys) == 1 else (min(q[0] for q in poly), max(q[0] for q in poly))
            up = [q for q in poly if q[1] > H + EPS]
            vmax = max(q[1] for q in up)
            crest = [q[0] for q in up if q[1] >= vmax - EPS]
            pk = (min(crest) + max(crest)) / 2.0              # middle of the highest stretch
            kl = min([(q[1] - H) / (q[0] - lo) for q in up if lo + EPS < q[0] <= pk] or [float("inf")])
            kr = min([(q[1] - H) / (hi - q[0]) for q in up if pk <= q[0] < hi - EPS] or [float("inf")])
            if not (EPS < kl < float("inf") and EPS < kr < float("inf")):
                continue
            pu = lo + (hi - lo) * kr / (kl + kr)
            out.append({"type": "prism", "name": _named(name, "roof"), "at": place(0, T, 0), "rot": rot,
                        "len": D - 2 * T, "pts": [[lo, H + 0.3 * m], [hi, H + 0.3 * m], [pu, H + kl * (pu - lo)]],
                        "color": "#8a4b3a"})
    elif roof == "gable":
        # Ridge parallel to the facade: rot + 90 turns the part's local x into the facade depth
        # and its local y into -u, so the prism runs from u = W back to u = 0.
        r90 = rot + 90.0 if rot + 90.0 <= 360 else rot - 270.0
        out.append({"type": "prism", "name": _named(name, "roof"), "at": place(W, 0, H + 0.3 * m),
                    "rot": r90, "len": W, "pts": [[0, 0], [D, 0], [D / 2.0, f.get("roof_h", 3.0)]],
                    "color": "#8a4b3a"})
    return out
