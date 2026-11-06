"""Random valid rhinospec specs, for stress-testing the Rhino builder.

  python tools/fuzz_specs.py N SEED OUT.jsonl

Each line is "id<TAB>spec-json". Every spec passes validation; whatever then fails in Rhino is a
builder bug (or a geometry case the planner should avoid), not a spec error.
"""
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # tools/dev -> repo
sys.path.insert(0, os.path.join(ROOT, "rhino"))
from rhinospec import SpecError, validate  # noqa: E402

CLASSES = ("window", "door", "shop", "balcony", "cornice", "molding", "pillar", "sill", "blind", "deco", "rustic", "quoin",
           "spandrel", "pediment", "arcade", "clad", "pipe", "finial")


def rnd_box(r, W, H):
    w = r.uniform(0.2, min(4.0, W / 2))
    h = r.uniform(0.15, min(4.0, H / 2))
    return [round(r.uniform(-0.5, W - w + 0.5), 3), round(r.uniform(-0.3, H - h + 0.3), 3), round(w, 3), round(h, 3)]


def facade(r):
    W, H = round(r.uniform(4, 40), 2), round(r.uniform(3, 40), 2)
    els = []
    for _ in range(r.randint(1, 25)):
        k = r.choice(CLASSES)
        el = {"k": k, "box": rnd_box(r, W, H)}
        if r.random() < 0.4:
            el["grid"] = [r.randint(1, 6), r.randint(1, 5), round(r.uniform(0.5, 4), 2), round(r.uniform(0.5, 4), 2)]
        if k in ("window", "door", "shop", "arcade"):
            if r.random() < 0.5:
                el["shape"] = r.choice(("rect", "arch", "seg") + (("round",) if k == "window" else ()))
            if r.random() < 0.5 and k != "arcade":
                el["bars"] = [r.randint(0, 3), r.randint(0, 3)]
        if k == "pillar" and r.random() < 0.5:
            el["shape"] = "round"
        if k == "finial":
            el["box"][1] = round(H - r.uniform(-0.3, 1.5), 3)  # on the parapet, or a little off it
            if r.random() < 0.6:
                el["shape"] = r.choice(("urn", "ball", "spire"))
        if k == "pediment":
            el["box"][1] = round(H - r.uniform(0, 1), 3)      # sits on the eaves, rises above them
        if k == "cornice" and r.random() < 0.6:
            el["shape"] = r.choice(("flat", "tri", "seg"))
        if r.random() < 0.3:
            el["d"] = round(r.uniform(0.01, 1.5), 3)
        if k in ("window", "door", "shop") and r.random() < 0.2 and el.get("shape") != "round":
            el["sur"] = round(r.uniform(0, 0.4), 3)
        if k == "deco" and r.random() < 0.6:
            el["shape"] = r.choice(("block", "console", "oval", "panel"))
        if k == "balcony" and r.random() < 0.6:
            el["rail"] = r.choice(("balustrade", "iron", "solid", "glass"))
        if k == "door" and r.random() < 0.6:
            el["leaf"] = r.choice(("panel", "glass", "garage"))
        if r.random() < 0.15:
            el["color"] = "#%06x" % r.randrange(1 << 24)
        els.append(el)
    f = {"type": "facade", "w": W, "h": H, "t": round(r.uniform(0.15, 0.8), 2), "els": els,
         "at": [round(r.uniform(-50, 50), 2), round(r.uniform(-50, 50), 2), 0], "rot": round(r.uniform(-180, 180), 1),
         "style": r.choice(("plain", "classic", "modern"))}
    if r.random() < 0.3:
        f["palette"] = {"wall": "#%06x" % r.randrange(1 << 24), "trim": "#%06x" % r.randrange(1 << 24),
                        "glass": "#%06x" % r.randrange(1 << 24)}
    if r.random() < 0.5:
        f.update(depth=round(r.uniform(2, 30), 2), floors=r.randint(1, 10),
                 roof=r.choice(("flat", "gable", "hip", "mansard", "none")), roof_h=round(r.uniform(0.5, 6), 2))
        if f["roof"] in ("hip", "mansard") and r.random() < 0.5:
            f["chimneys"] = [round(r.uniform(0, W), 2) for _ in range(r.randint(1, 4))]
            els.append({"k": "window", "box": [round(r.uniform(0, W - 1), 2), H + 0.2, 0.8, 1.0]})   # a dormer
    if r.random() < 0.3 and f.get("roof") not in ("hip", "mansard"):
        # A gable, a stepped gable or a raised parapet above the eaves, with a window in it.
        kind = r.choice(("gable", "steps", "parapet", "twin"))
        if kind == "gable":
            top = [[round(r.uniform(0.2, 0.8) * W, 2), round(H + r.uniform(0.5, 8), 2)]]
        elif kind == "twin":
            top = [[round(W * 0.25, 2), round(H + r.uniform(0.5, 5), 2)], [round(W / 2, 2), H],
                   [round(W * 0.75, 2), round(H + r.uniform(0.5, 5), 2)]]
        else:
            n = r.randint(1, 4) if kind == "steps" else 1
            rise = [round(r.uniform(0.3, 1.5), 2) for _ in range(n)]
            xs = sorted(round(r.uniform(0, W), 2) for _ in range(2 * n))
            top, v = [], H
            for i in range(n):
                v += rise[i]
                top += [[xs[i], round(v - rise[i], 2)], [xs[i], round(v, 2)]]
            for i in range(n - 1, -1, -1):
                top += [[xs[2 * n - 1 - i], round(v, 2)], [xs[2 * n - 1 - i], round(v - rise[i], 2)]]
                v -= rise[i]
        f["top"] = top
        f.pop("chimneys", None)
        f["els"] = [e for e in els if e["box"][1] < H]
        if not f["els"]:
            f["els"] = [{"k": "window", "box": [1, 1, 1, 1]}]
        f["els"].append({"k": "window", "box": [round(W * 0.45, 2), round(H + 0.1, 2), round(W * 0.1, 2), 0.4],
                         "shape": r.choice(("rect", "arch", "round"))})
    return f


def block(r):
    """A block whose faces are random facades (front always, others sometimes)."""
    f = facade(r)
    W, D = f["w"], round(r.uniform(4, 30), 2)
    faces = {"front": {"els": f["els"]}}
    for side in ("right", "back", "left"):
        if r.random() < 0.4:
            faces[side] = {"els": [{"k": "window", "box": [1, 1, 1, 1.5], "grid": [3, 2, 2.5, 3]}]}
    return {"type": "block", "w": W, "d": D, "h": f["h"], "t": min(f["t"], W / 2.5, D / 2.5), "faces": faces,
            "floors": r.randint(1, 10), "roof": r.choice(("flat", "gable", "hip", "mansard", "none")),
            "roof_h": round(r.uniform(0.5, 6), 2), "rot": f["rot"], "at": f["at"], "style": f["style"],
            "dormers": r.choice((0, 0, 1, 3, 8)), "chimneys": r.choice((0, 0, 1, 2, 5))}


def primitive(r):
    t = r.choice(("box", "cyl", "cone", "sphere", "torus", "extrude", "prism", "revolve", "loft", "pipe", "panel"))
    at = [round(r.uniform(-20, 20), 2) for _ in range(3)]
    p = {"type": t, "at": at, "rot": round(r.uniform(-180, 180), 1)}
    sq = [[0, 0], [2, 0], [2, 1.5], [0, 1.5]]
    if t == "box":
        p["size"] = [round(r.uniform(0.05, 5), 2) for _ in range(3)]
    elif t in ("cyl", "cone"):
        p.update(r=round(r.uniform(0.05, 3), 2), h=round(r.uniform(0.05, 5), 2))
        if t == "cone":
            p["r2"] = round(r.choice((0, r.uniform(0, 3))), 2)
    elif t == "sphere":
        p["r"] = round(r.uniform(0.05, 3), 2)
    elif t == "torus":
        R = r.uniform(0.5, 4)
        p.update(R=round(R, 2), r=round(r.uniform(0.05, R * 0.9), 2))
    elif t == "extrude":
        p.update(pts=[[round(x * r.uniform(0.5, 2), 2), round(y * r.uniform(0.5, 2), 2)] for x, y in sq], h=round(r.uniform(0.1, 4), 2))
    elif t == "prism":
        p.update(pts=[[0, 0], [round(r.uniform(0.5, 4), 2), 0], [round(r.uniform(0, 4), 2), round(r.uniform(0.3, 3), 2)]], len=round(r.uniform(0.1, 6), 2))
    elif t == "revolve":
        zs = sorted(round(r.uniform(0, 4), 2) for _ in range(4))
        p["profile"] = [[0, zs[0]]] + [[round(r.uniform(0.1, 2), 2), z] for z in zs[1:-1]] + [[0, zs[-1] + 0.1]]
    elif t == "loft":
        p["sections"] = [{"pts": [[x * s, y * s] for x, y in sq], "z": z} for s, z in ((1, 0), (round(r.uniform(0.2, 1.5), 2), round(r.uniform(0.5, 4), 2)))]
    elif t == "pipe":
        p.update(path=[[round(r.uniform(-5, 5), 2) for _ in range(3)] for _ in range(r.randint(2, 5))], r=round(r.uniform(0.02, 0.3), 2))
    elif t == "panel":
        w, h = round(r.uniform(2, 8), 2), round(r.uniform(2, 6), 2)
        holes = []
        for _ in range(r.randint(0, 4)):
            hw, hh = round(r.uniform(0.2, w / 3), 2), round(r.uniform(0.2, h / 3), 2)
            hole = [round(r.uniform(0.05, w - hw - 0.05), 2), round(r.uniform(0.05, h - hh - 0.05), 2), hw, hh]
            if r.random() < 0.4:
                hole.append(r.randint(0, 2))
            if all(not (hole[0] < o[0] + o[2] + 0.01 and o[0] < hole[0] + hole[2] + 0.01 and
                        hole[1] < o[1] + o[3] + 0.01 and o[1] < hole[1] + hole[3] + 0.01) for o in holes):
                holes.append(hole)
        p.update(size=[w, h], t=round(r.uniform(0.05, 0.6), 2), holes=holes)
    if r.random() < 0.2 and t in ("box", "cyl", "extrude"):
        p["cut"] = [{"type": "cyl", "at": [at[0], at[1], at[2] - 1], "r": round(r.uniform(0.05, 1), 2), "h": 10}]
    return p


def make(r, i):
    pick = lambda: facade(r) if r.random() < 0.45 else block(r) if r.random() < 0.4 else primitive(r)
    parts = [pick() for _ in range(r.randint(1, 4))]
    return {"units": r.choice(("m", "cm", "mm")) if r.random() < 0.1 else "m", "layer": "FUZZ", "clear": True, "parts": parts}


def main(argv):
    n, seed, out = int(argv[1]), int(argv[2]), argv[3]
    r = random.Random(seed)
    kept = rejected = 0
    with open(out, "w", encoding="utf-8") as fh:
        while kept < n:
            spec = make(r, kept)
            try:
                validate(spec)
            except SpecError:
                rejected += 1
                continue
            fh.write("fuzz%04d\t%s\n" % (kept, json.dumps(spec, separators=(",", ":"))))
            kept += 1
    print(json.dumps({"written": kept, "rejected_while_generating": rejected}))


if __name__ == "__main__":
    main(sys.argv)
