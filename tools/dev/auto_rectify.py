"""EXPERIMENT, NOT USED BY THE PLUGIN. Result (2026-11-06, tools/dev, measured with near-vertical LSD
segments on hznu photos): median residual lean 3.47 deg with MoGe-2 at 1024 px against 1.55 deg for
Claude's four corners + rectify.py (0.79 deg with the dataset's own homography) on the three baseline
photos c_0075, c_0174, c_0227, and 2.38 deg against 5.38 deg in the raw photo over 20 photos, worse
than the photo itself on 5 of them; the same photo gave 2.1 / 12.7 / 1.26 deg at 512 / 768 / 1024 px
(a different wall picked). Full-size 24 MP input needed ~20 GB of RAM before infer_side was added.
Kept so the test is not repeated blindly.

Straightens a facade photo without reading its corners: MoGe-2 (microsoft/MoGe, MIT) gives every
pixel a 3D point in metres and a surface normal; the dominant wall plane is fitted to them and a
virtual camera turned to face it squarely (homography K R K^-1, the same camera rotated).

    data\\venv-det\\Scripts\\python.exe tools/auto_rectify.py PHOTO OUT.jpg [--side 1600]

Prints {"H": photo -> OUT homography, "normal", "tilt_deg", "pan_deg", "inliers", "m_per_px"}:
m_per_px is the metric size of one OUT pixel on the wall plane, from MoGe's metric depth. The
weights (Ruicheng/moge-2-vitl-normal, 1.3 GB) load from HF_HOME (data/hf-cache by default) and
nothing is downloaded once they are there (HF_HUB_OFFLINE=1).

Assumes the photo is held roughly level (no roll): the wall's vertical is the camera's up made
perpendicular to the wall normal.
"""
import argparse
import json
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # tools/dev -> repo
WEIGHTS = "Ruicheng/moge-2-vitl-normal"
_MODEL = []


def model():
    if not _MODEL:
        os.environ.setdefault("HF_HOME", os.path.join(ROOT, "data", "hf-cache"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        import torch
        from moge.model.v2 import MoGeModel
        dev = "cuda" if torch.cuda.is_available() else "cpu"
        _MODEL.append((MoGeModel.from_pretrained(WEIGHTS).to(dev).eval(), dev))
    return _MODEL[0]


def geometry(rgb):
    """rgb uint8 HxWx3 -> (points HxWx3 metres, normals HxWx3, valid HxW, K 3x3 in pixels), camera
    coordinates x right, y down, z forward."""
    import torch
    m, dev = model()
    h, w = rgb.shape[:2]
    x = torch.tensor(rgb / 255.0, dtype=torch.float32, device=dev).permute(2, 0, 1)
    with torch.no_grad():
        out = m.infer(x)
    K = out["intrinsics"].cpu().numpy().astype(np.float64)
    K[0] *= w
    K[1] *= h
    return (out["points"].cpu().numpy(), out["normal"].cpu().numpy(), out["mask"].cpu().numpy(), K)


def wall_plane(points, normals, valid, region=None, step=4, seed=0):
    """Dominant vertical plane: normals that are nearly horizontal (a wall), grouped by direction,
    the fullest group refined by RANSAC on its 3D points. Returns (unit normal facing the camera,
    offset d with n.p = d, inlier share)."""
    P = points[::step, ::step].reshape(-1, 3)
    N = normals[::step, ::step].reshape(-1, 3)
    ok = valid[::step, ::step].reshape(-1)
    if region is not None:
        ok &= region[::step, ::step].reshape(-1)
    ok &= np.abs(N[:, 1]) < 0.35            # vertical surfaces: little of the normal along the camera's y
    P, N = P[ok], N[ok]
    if len(P) < 50:
        raise ValueError("no wall found")
    N = np.where((N[:, 2] > 0)[:, None], -N, N)   # every normal towards the camera (z negative)
    az = np.degrees(np.arctan2(N[:, 0], -N[:, 2]))
    hist, edges = np.histogram(az, bins=36, range=(-90, 90))
    b = int(hist.argmax())
    lo, hi = edges[max(0, b - 1)], edges[min(len(edges) - 1, b + 2)]
    sel = (az >= lo) & (az <= hi)
    P, N = P[sel], N[sel]
    rng = np.random.default_rng(seed)
    depth = np.median(P[:, 2])
    tol = 0.02 * depth                     # 2 % of the distance: bricks and window recesses stay in
    best, best_in = None, None
    for _ in range(300):
        i = rng.choice(len(P), 3, replace=False)
        n = np.cross(P[i[1]] - P[i[0]], P[i[2]] - P[i[0]])
        if np.linalg.norm(n) < 1e-9:
            continue
        n /= np.linalg.norm(n)
        if abs(n[1]) > 0.35:
            continue
        inl = np.abs(P @ n - P[i[0]] @ n) < tol
        if best_in is None or inl.sum() > best_in.sum():
            best, best_in = n, inl
    Q = P[best_in]
    c = Q.mean(axis=0)
    n = np.linalg.svd(Q - c)[2][-1]
    if n[2] > 0:
        n = -n
    return n, float(n @ c), float(best_in.mean())


def rotation(n):
    """Rows: the virtual camera's x, y, z in the photo camera's frame; z looks into the wall."""
    f = -n / np.linalg.norm(n)
    up = np.array([0.0, -1.0, 0.0])
    up = up - (up @ f) * f
    up /= np.linalg.norm(up)
    y = -up
    x = np.cross(y, f)
    return np.stack([x, y, f])


def homography(n, K, w, h, side=1600, region=None):
    """photo -> straightened image: K R K^-1, then scaled and shifted so the region (default the
    whole photo) fits a canvas whose long side is side pixels."""
    H = K @ rotation(n) @ np.linalg.inv(K)
    if region is not None and region.any():
        ys, xs = np.nonzero(region)
        pts = np.stack([xs, ys, np.ones_like(xs)], 1)[:: max(1, len(xs) // 4000)].astype(np.float64)
    else:
        pts = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], np.float64)
    q = (H @ pts.T).T
    q = q[:, :2] / q[:, 2:3]
    x0, y0 = q.min(0)
    x1, y1 = q.max(0)
    s = side / max(x1 - x0, y1 - y0)
    A = np.array([[s, 0, -s * x0], [0, s, -s * y0], [0, 0, 1]])
    return A @ H, (int(round((x1 - x0) * s)), int(round((y1 - y0) * s))), s


def rectify(path, out=None, side=1600, region=None, infer_side=1024):
    """MoGe runs on a copy whose long side is infer_side (full-size 12 MP photos need tens of GB
    for the per-pixel output); K is scaled back so H and m_per_px refer to the original photo."""
    import cv2
    bgr = cv2.imread(path)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    r = min(1.0, infer_side / max(w, h))
    small = cv2.resize(rgb, (round(w * r), round(h * r)), interpolation=cv2.INTER_AREA) if r < 1 else rgb
    points, normals, valid, K = geometry(small)
    K[:2] /= r
    reg_s = None
    if region is not None:
        reg_s = cv2.resize(region.astype(np.uint8), small.shape[1::-1], interpolation=cv2.INTER_NEAREST) > 0
    n, d, share = wall_plane(points, normals, valid, reg_s)
    H, size, s = homography(n, K, w, h, side, region)
    # metres per output pixel on the wall: the plane at distance d seen by a camera of focal fx
    m_per_px = abs(d) / (K[0, 0] * s)
    if out:
        cv2.imwrite(out, cv2.warpPerspective(bgr, H, size, flags=cv2.INTER_AREA))
    tilt = float(np.degrees(np.arcsin(np.clip(-n[1], -1, 1))))
    pan = float(np.degrees(np.arctan2(n[0], -n[2])))
    return {"H": np.round(H, 8).tolist(), "size": list(size), "normal": np.round(n, 4).tolist(),
            "tilt_deg": round(tilt, 2), "pan_deg": round(pan, 2), "inliers": round(share, 3),
            "m_per_px": round(float(m_per_px), 5)}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photo")
    ap.add_argument("out")
    ap.add_argument("--side", type=int, default=1600)
    a = ap.parse_args(argv[1:])
    print(json.dumps(rectify(a.photo, a.out, a.side)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
