# -*- coding: utf-8 -*-
"""Cheap sanity checks on planned parts, before any geometry exists (pure Python).

The idea, borrowed from how agent tools verify their own builds: a number in the summary
("2 floating parts: gamba 3, ...") catches most modelling slips without a screenshot.
Bounding boxes are exact for boxes and panels and conservative for the other primitives.
"""
from __future__ import division

import math

TOL_M = 0.01          # parts closer than 1 cm count as touching
PER_M = {"mm": 1000.0, "cm": 100.0, "m": 1.0}
MAX_PAIRS = 2000000   # skip the pairwise test on huge models rather than stall


def _transformed(p, xs, ys, zs):
    """World box of the local box xs x ys x zs after tilt (x then y), rot (z) and at."""
    at, rot = p["at"], p.get("rot", 0.0)
    tx, ty = p.get("tilt", [0.0, 0.0])
    cx, sx = math.cos(math.radians(tx)), math.sin(math.radians(tx))
    cy, sy = math.cos(math.radians(ty)), math.sin(math.radians(ty))
    cz, sz = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    pts = []
    for x in xs:
        for y in ys:
            for z in zs:
                y1, z1 = cx * y - sx * z, sx * y + cx * z          # about x
                x2, z2 = cy * x + sy * z1, -sy * x + cy * z1       # about y
                x3, y3 = cz * x2 - sz * y1, sz * x2 + cz * y1      # about z
                pts.append((at[0] + x3, at[1] + y3, at[2] + z2))
    return [min(q[0] for q in pts), min(q[1] for q in pts), min(q[2] for q in pts),
            max(q[0] for q in pts), max(q[1] for q in pts), max(q[2] for q in pts)]


def bbox(p):
    """[x0, y0, z0, x1, y1, z1] in spec units for one validated primitive."""
    t = p["type"]
    _rotated = lambda at, rot, xs, ys, zs: _transformed(p, xs, ys, zs)
    at, rot = p["at"], p.get("rot", 0.0)
    if t == "box":
        sx, sy, sz = p["size"]
        return _rotated(at, rot, (0, sx), (0, sy), (0, sz))
    if t == "panel":
        w, h = p["size"]
        return _rotated(at, rot, (0, w), (0, p["t"]), (0, h))
    if t in ("cyl", "cone"):
        r = max(p["r"], p.get("r2", 0))
        return _rotated(at, rot, (-r, r), (-r, r), (0, p["h"]))
    if t == "sphere":
        r = p["r"]
        return _rotated(at, rot, (-r, r), (-r, r), (-r, r))
    if t == "torus":
        R = p["R"] + p["r"]
        return _rotated(at, rot, (-R, R), (-R, R), (-p["r"], p["r"]))
    if t == "revolve":
        r = max(q[0] for q in p["profile"])
        zs = [q[1] for q in p["profile"]]
        return _rotated(at, rot, (-r, r), (-r, r), (min(zs), max(zs)))
    if t == "extrude":
        xs, ys = [q[0] for q in p["pts"]], [q[1] for q in p["pts"]]
        return _rotated(at, rot, (min(xs), max(xs)), (min(ys), max(ys)), (0, p["h"]))
    if t == "prism":
        xs, zs = [q[0] for q in p["pts"]], [q[1] for q in p["pts"]]
        return _rotated(at, rot, (min(xs), max(xs)), (0, p["len"]), (min(zs), max(zs)))
    if t == "loft":
        xs = [q[0] for s in p["sections"] for q in s["pts"]]
        ys = [q[1] for s in p["sections"] for q in s["pts"]]
        zs = [s["z"] for s in p["sections"]]
        return _rotated(at, rot, (min(xs), max(xs)), (min(ys), max(ys)), (min(zs), max(zs)))
    if t == "pipe":
        # the path is relative to at, like every other local frame (the builder moves it by at)
        xs, ys, zs = zip(*p["path"])
        r = p["r"]
        return _rotated(at, rot, (min(xs) - r, max(xs) + r), (min(ys) - r, max(ys) + r), (min(zs) - r, max(zs) + r))
    raise ValueError("no bbox for %s" % t)


def _touch(a, b, tol):
    return all(a[i] <= b[i + 3] + tol and b[i] <= a[i + 3] + tol for i in range(3))


def floating(parts, tol=TOL_M):
    """Names (or indices) of parts that neither rest on the model's lowest level nor touch any
    other part. Returns (labels, skipped) where skipped is True on models too large to check."""
    n = len(parts)
    if n < 2 or n * n > MAX_PAIRS:
        return [], n * n > MAX_PAIRS
    boxes = [bbox(p) for p in parts]
    ground = min(b[2] for b in boxes)
    # Sweep along x: only parts whose x ranges overlap can touch.
    order = sorted(range(n), key=lambda i: boxes[i][0])
    touched = [boxes[i][2] <= ground + tol for i in range(n)]
    for a_pos, i in enumerate(order):
        bi = boxes[i]
        for j in order[a_pos + 1:]:
            bj = boxes[j]
            if bj[0] > bi[3] + tol:
                break
            if _touch(bi, bj, tol):
                touched[i] = touched[j] = True
    return [parts[i].get("name") or "parts[%d] %s" % (i, parts[i]["type"]) for i in range(n) if not touched[i]], False


def report(parts, units="m"):
    """Summary fields for run()/check(): {} when everything touches."""
    labels, skipped = floating(parts, TOL_M * PER_M.get(units, 1.0))
    if skipped:
        return {"checks": "skipped (too many parts)"}
    if not labels:
        return {}
    return {"floating": len(labels), "floating_examples": labels[:3]}
