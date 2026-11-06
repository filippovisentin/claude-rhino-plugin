"""Ranks CMP photos by how clean the facade is: little vegetation in front, facade filling the
frame, regular windows. Prints the best N ids with their metrics.

  python tools/clean_pick.py N
"""
import json
import statistics
import sys

import numpy as np
from PIL import Image

_HERE = __import__("os").path.dirname(__import__("os").path.abspath(__file__))
sys.path[:0] = [_HERE, __import__("os").path.dirname(_HERE)]  # tools/dev, then the runtime tools
import facade_bench as fb  # noqa: E402


def metrics(fid):
    (fx0, fy0, fx1, fy1), objs = fb.read_annotation(fid)
    with Image.open(fb._paths(fid) + ".jpg") as im:
        im = im.convert("RGB")
        im.thumbnail((256, 256))
        hsv = np.asarray(im.convert("HSV"), dtype=np.float64) / 255.0
    H, W = hsv.shape[:2]
    roi = hsv[int(fy0 * H):int(fy1 * H), int(fx0 * W):int(fx1 * W)]
    h, s, v = roi[..., 0], roi[..., 1], roi[..., 2]
    green = float(((h > 0.17) & (h < 0.47) & (s > 0.2) & (v > 0.12)).mean()) if roi.size else 1.0
    dark = float((v < 0.12).mean()) if roi.size else 1.0      # black borders from rectification
    wins = [o for o in objs if o[0] == "window"]
    ws = [o[3] - o[1] for o in wins]
    hs = [o[4] - o[2] for o in wins]
    cv = (statistics.pstdev(ws) / statistics.mean(ws) + statistics.pstdev(hs) / statistics.mean(hs)) / 2 if len(wins) > 2 else 9
    cover = (fx1 - fx0) * (fy1 - fy0)
    score = green * 4 + dark * 2 + cv + (1 - cover) + (0 if 8 <= len(wins) <= 60 else 1)
    return {"id": fid, "score": round(score, 3), "green": round(green, 3), "dark": round(dark, 3),
            "win_cv": round(cv, 2), "cover": round(cover, 2), "windows": len(wins)}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    rows = sorted((metrics(f) for f in fb.all_ids()), key=lambda r: r["score"])
    for r in rows[:n]:
        print(json.dumps(r))
