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
    "blind": "#4f6b52", "deco": "#cbbfa6", "balcony": "#6f6f6f",
}
# Default depth per class: recess for openings, projection for everything else.
DEPTH = {"window": 0.12, "door": 0.15, "shop": 0.10, "cornice": 0.30, "molding": 0.06,
         "pillar": 0.12, "sill": 0.06, "blind": 0.04, "deco": 0.04, "balcony": 1.0}


OPENING_SHAPES = ("rect", "arch", "seg")
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
    plane. Curved tops are polylines; the bounding box is exactly [u, v, w, h]."""
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


def facade_elements(f):
    """Expands grids and clips every element to the facade. Returns [(k, [u, v, w, h], el)]."""
    out = []
    for el in f["els"]:
        u0, v0, w, h = el["box"]
        nx, ny, du, dv = el["grid"]
        offsets = el.get("offs") or [[i * du, j * dv] for j in range(ny) for i in range(nx)]
        min_el = MIN_EL * f.get("per_m", 1.0)
        for ou, ov in offsets:
            u, v = u0 + ou, v0 + ov
            cu0, cv0 = max(u, 0.0), max(v, 0.0)
            cu1, cv1 = min(u + w, f["w"]), min(v + h, f["h"])
            if cu1 - cu0 >= min_el and cv1 - cv0 >= min_el:
                out.append((el["k"], [cu0, cv0, cu1 - cu0, cv1 - cv0], el))
    return out


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
    els = facade_elements(f)
    raw = [(r, el.get("shape", "rect")) for k, r, el in els if k in ("window", "door", "shop")]
    key = lambda r: tuple(round(x, 9) for x in r)
    shape_of = dict((key(r), sh) for r, sh in raw)
    # Merged openings keep their shape only when nothing was merged into them.
    openings = [(r, shape_of.get(key(r), "rect")) for r in _merge_rects([r for r, _ in raw])]
    eps = 1e-3 * m
    inside = lambda r: r[0] > eps and r[1] > eps and r[0] + r[2] < W - eps and r[1] + r[3] < H - eps
    holes = [r + [OPENING_SHAPES.index(sh)] if sh != "rect" else r for r, sh in openings if inside(r)]
    edge = [(r, sh) for r, sh in openings if not inside(r)]

    wall = {"type": "panel", "name": _named(name, "wall"), "at": place(0, 0, 0), "rot": rot,
            "size": [W, H], "t": T, "holes": holes, "color": wall_color}
    if edge:
        # Openings touching the facade outline (shop fronts, doors on the ground line) can't be
        # inner loops of an extrusion: cut them with their outline instead, slightly oversized.
        wall["cut"] = [{"type": "prism", "at": place(0, -T, 0), "rot": rot, "len": 3 * T,
                        "pts": opening_outline(r[0] - eps, r[1] - eps, r[2] + 2 * eps, r[3] + 2 * eps, sh)}
                       for r, sh in edge]
    parts = [wall]

    for n, (k, (u, v, w, h), el) in enumerate(els):
        tag = "%s %d" % (k, n)
        depth = el.get("d", DEPTH[k] * m)
        shape = el.get("shape")
        if k in ("window", "door", "shop") and shape in ("arch", "seg"):
            r = min(depth, T - GLASS_ * 2)
            fr = min(FRAME_, w / 4.0, h / 4.0)
            iu, iv, iw, ih = u + fr, v + fr, w - 2 * fr, h - 2 * fr
            if iw < MIN_ or ih < MIN_:
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
            leaf = COLORS["door"] if k == "door" else COLORS["glass"]
            leaf_t = 0.05 * m if k == "door" else GLASS_
            parts.append(box(tag + (" leaf" if k == "door" else " glass"), iu, r + 0.03 * m, iv, iw, leaf_t, ih, leaf))
            nb_v, nb_h = el.get("bars", [0, 0])
            for b in range(nb_v):
                bu = iu + iw * (b + 1) / (nb_v + 1.0) - BAR_ / 2
                parts.append(box(tag + " bar", bu, r + 0.02 * m, iv, BAR_, 0.04 * m, ih, COLORS["frame"]))
            for b in range(nb_h):
                bv = iv + ih * (b + 1) / (nb_h + 1.0) - BAR_ / 2
                parts.append(box(tag + " bar", iu, r + 0.02 * m, bv, iw, 0.04 * m, BAR_, COLORS["frame"]))
        elif k == "balcony":
            slab_t = min(0.15 * m, h)
            rail_t = min(0.05 * m, w / 4.0, depth / 2.0)
            parts.append(box(tag + " slab", u, -depth, v, w, depth, slab_t, COLORS["balcony"]))
            rail_h = h - slab_t
            if rail_h > MIN_:
                parts.append(box(tag + " rail", u, -depth, v + slab_t, w, rail_t, rail_h, COLORS["balcony"]))
                for side_u in (u, u + w - rail_t):
                    parts.append(box(tag + " side", side_u, -depth, v + slab_t, rail_t, depth, rail_h, COLORS["balcony"]))
        elif k == "cornice" and shape in ("tri", "seg"):
            # Pediment: the hood outline in the facade plane, pushed out by its depth.
            if shape == "tri":
                pts = [[u, v], [u + w, v], [u + w / 2.0, v + h]]
            else:
                arc = opening_outline(u, v - h, w, 2 * h, "seg")
                pts = [[u, v], [u + w, v]] + [q for q in arc[2:] if q[1] > v]
            parts.append({"type": "prism", "name": _named(name, tag), "at": place(0, -depth, 0), "rot": rot,
                          "len": depth, "pts": pts, "color": COLORS[k]})
        elif k in ("molding", "cornice") and depth >= 0.15 * m and h >= 0.12 * m:
            # Corbelled profile: three steps growing outward toward the top.
            z = v
            for frac_h, frac_d in ((0.4, 0.5), (0.3, 0.8), (0.3, 1.0)):
                parts.append(box(tag, u, -depth * frac_d, z, w, depth * frac_d, h * frac_h, COLORS[k]))
                z += h * frac_h
        else:
            parts.append(box(tag, u, -depth, v, w, depth, h, COLORS[k]))

    if f.get("depth", 0.0) > 2 * T:
        parts.extend(_volume(f, place, box, name, wall_color, m))
    return _categorize(parts, name, f.get("color"))


SUBPART = {"frame": "frames", "glass": "glass", "bar": "bars", "leaf": "leaves"}


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
                cat += "/" + SUBPART[words[-1]]
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
             "els": b["faces"].get(key, []), "name": "%s %s" % (name, key), "depth": 0.0}
        if "color" in b:
            f["color"] = b["color"]
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
    return parts


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
