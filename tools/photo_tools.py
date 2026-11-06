"""Reading aids on any photo, for Claude to check and refine a px facade reading.

    node "<plugin>/scripts/run-tool.mjs" overlay PHOTO SPEC.json OUT.jpg
    node "<plugin>/scripts/run-tool.mjs" crop PHOTO x0 y0 x1 y1 OUT.jpg [--size 768]

overlay  draws the px boxes of SPEC.json over the photo (grids expanded), one colour per element
         family. SPEC.json is a spec with one facade part with px, or a detect_facade draft
         ({"els": [...]}). The boxes must be in this photo's pixels.
crop     cuts box x0 y0 x1 y1 (this photo's pixels) and enlarges it so its long side is --size
         pixels; prints {"origin": [x0, y0], "scale": s}: a pixel (xc, yc) of the crop is
         (x0 + xc / s, y0 + yc / s) in the photo, the frame every px box is read in.
Needs Pillow.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "rhino"))

COLORS = {"window": "#00a0ff", "door": "#ff8000", "shop": "#ff00ff", "balcony": "#00ff00", "cornice": "#ff0000",
          "molding": "#ffff00", "pillar": "#00ffff", "sill": "#8000ff", "blind": "#008000", "deco": "#804000",
          "rustic": "#a0a0a0", "quoin": "#606060", "spandrel": "#303840", "pediment": "#ffa0a0",
          "clad": "#b0a080", "pipe": "#80c0c0", "finial": "#c0a0ff"}


def facade_part(spec):
    """The one facade part of a spec, validated by rhinospec."""
    from rhinospec import spec as S
    parts = [p for p in spec.get("parts", []) if isinstance(p, dict) and p.get("type") == "facade"]
    if len(parts) != 1:
        raise S.SpecError("spec must hold exactly one facade part")
    return S._facade(parts[0], "parts[0]")


def expand_px(el):
    """Pixel boxes of one px element: grid steps or explicit xs/ys start positions."""
    x0, y0, x1, y1 = el["box"]
    if "xs" in el or "ys" in el:
        xs, ys = el.get("xs", [x0]), el.get("ys", [y0])
        return [[x, y, x + x1 - x0, y + y1 - y0] for y in ys for x in xs]
    nx, ny, dx, dy = el.get("grid", [1, 1, 0, 0])
    return [[x0 + i * dx, y0 + j * dy, x1 + i * dx, y1 + j * dy] for j in range(ny) for i in range(nx)]


def px_boxes(pred_spec):
    """Pixel boxes of a px facade, grids expanded: [(k, [x0, y0, x1, y1])]."""
    f = [q for q in pred_spec["parts"] if q.get("type") == "facade"][0]
    facade_part(pred_spec)   # validates
    return [(el["k"], b) for el in f["els"] for b in expand_px(el)]


def draw_boxes(im, boxes, width=2):
    from PIL import ImageDraw
    draw = ImageDraw.Draw(im)
    for k, b in boxes:
        draw.rectangle([float(v) for v in b], outline=COLORS.get(k, "#ffffff"), width=width)
    return im


def overlay(photo, spec_path, out):
    """Draws the spec's (or draft's) px boxes over the photo into out; returns the box count."""
    from PIL import Image
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)
    if "parts" in spec:
        boxes = px_boxes(spec)
    else:
        boxes = [(el["k"], b) for el in spec.get("els", []) for b in expand_px(el)]
    with Image.open(photo) as src:
        im = draw_boxes(src.convert("RGB"), boxes)
    im.save(out, quality=85)
    return len(boxes)


def crop(photo, box, out, size=768):
    """Crops box (photo pixels) and enlarges it to size on its long side; returns origin and scale."""
    from PIL import Image
    x0, y0, x1, y1 = [float(v) for v in box]
    with Image.open(photo) as im:
        w, h = im.size
        if not (0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h):
            raise ValueError("crop box must lie inside the %dx%d photo, with x0 < x1 and y0 < y1" % (w, h))
        scale = min(size / (x1 - x0), size / (y1 - y0))
        part = im.convert("RGB").crop((int(x0), int(y0), int(x1), int(y1)))
        part = part.resize((max(1, round((x1 - x0) * scale)), max(1, round((y1 - y0) * scale))), Image.LANCZOS)
    part.save(out, quality=88)
    num = lambda v: int(v) if float(v).is_integer() else round(v, 4)  # noqa: E731
    return {"origin": [num(x0), num(y0)], "scale": num(scale)}


def main(argv):
    try:
        if argv[:1] == ["overlay"] and len(argv) == 4:
            print(json.dumps({"boxes": overlay(argv[1], argv[2], argv[3]), "out": argv[3]}))
            return 0
        if argv[:1] == ["crop"] and len(argv) in (7, 9):
            size = 768
            if len(argv) == 9:
                if argv[7] != "--size":
                    raise ValueError("unknown option %s" % argv[7])
                size = int(argv[8])
            print(json.dumps(crop(argv[1], argv[2:6], argv[6], size)))
            return 0
    except (ValueError, OSError, KeyError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
