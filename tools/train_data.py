"""Training data and offline training for two local models that make photo reading simpler.

  scene  (YOLO segmentation): what is not the building and has to be ignored or masked out before
         reading the facade: sky, vegetation, vehicles, people, the ground, and the building itself
  parts  (YOLO detection): the parts of the building the 3D builder needs, in its own vocabulary:
         CMP's ten classes plus pediments (triangular, segmental), arches, oculi and finials

Run with the detector environment (Ultralytics, OpenCV, CUDA): data\\venv-det\\Scripts\\python.exe

  python tools/train_data.py sources                    datasets, licences, what is on disk
  python tools/train_data.py download NAME [NAME ...]   monumai | oxford | seg-weights (needs network)
  python tools/train_data.py scene [--limit N]          -> data/yolo-scene (+ scene.yaml)
  python tools/train_data.py parts [--limit N] [--no-teacher]   -> data/yolo-parts (+ parts.yaml)
  python tools/train_data.py train scene|parts [--epochs 120] [--batch 8] [--imgsz 1024] [--model PT] [--hours H]

Training runs offline (YOLO_OFFLINE=1, settings and font in data/det-runs/cfg) into data/det-runs/
<scene11s|parts11s>. Downloads are separate and only happen with `download`.

Missing labels: every dataset annotates only some classes, and an unlabelled object teaches the
model that it is background. `parts` fills each image's missing CMP classes with yesterday's
detectors (all11s for windows and doors, cmp11s for the rest; confidence >= 0.5) and `scene` adds people and vehicles from the
COCO segmentation model (yolo11s-seg) where a dataset does not label them. The photos Claude read
blind (data/work/*.pred.json) never enter training: they stay the test set, as in facade_yolo.py.
"""
import argparse
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import facade_bench as FB  # noqa: E402
import facade_yolo as FY  # noqa: E402

DATA = os.path.join(FB.ROOT, "data")
RUNS = os.path.join(DATA, "det-runs")
CFG = os.path.join(RUNS, "cfg")
# Teachers for the classes a source does not label, each for what it learnt with complete labels:
# all11s saw modern photos but only their windows and doors (it learnt that modern facades have no
# sills or cornices), cmp11s saw every class on historic facades.
# monumai11s (MonuMAI alone, `parts --sources monumai --name monumai`, then `train monumai`) for the
# new classes: in the first parts11s they were unlabelled on every non-monument photo, and the
# model learnt to suppress arches and pediments everywhere else.
NEW = {"arch", "pediment", "pediment_seg", "oculus", "finial"}
TEACHERS = [(os.path.join(RUNS, "all11s", "weights", "best.pt"), {"window", "door"}),
            (os.path.join(RUNS, "cmp11s", "weights", "best.pt"), set(FY.NAMES) - {"window", "door"}),
            (os.path.join(RUNS, "monumai11s", "weights", "best.pt"), NEW)]
SEG_WEIGHTS = os.path.join(RUNS, "yolo11s-seg.pt")

SCENE = ["building", "sky", "vegetation", "vehicle", "person", "ground", "pole"]   # pole: lamps, poles, signs
PARTS = FY.NAMES + ["pediment", "pediment_seg", "arch", "oculus", "finial"]

SOURCES = {
    # name: (path, what it gives, licence, download)
    "cmp": (os.path.join(DATA, "cmp"), "606 rectified historic facades, 12 classes", "CC BY-SA 4.0", "on disk"),
    "hznu": (os.path.join(DATA, "hznu"), "624 modern Hangzhou facades: windows, doors, building, tree, car, sky",
             "CC BY 4.0", "on disk"),
    "cfp": (os.path.join(DATA, "cfp"), "street views (Osaka, Tokyo, Toronto, Shanghai): windows, doors",
            "no licence stated", "on disk"),
    "labelme": (os.path.join(DATA, "labelmefacade"), "945 street photos, pixel masks: building, window, door, "
                "car, vegetation, sky, road, pavement", "research and non-commercial use", "on disk"),
    "monumai": (os.path.join(DATA, "monumai"), "1514 monument facades (Gothic, Renaissance, Baroque, "
                "Hispano-Muslim), 15 element classes, Pascal VOC boxes", "CC BY 4.0",
                "git clone --depth 1 https://github.com/ari-dasci/OD-MonuMAI (about 1.1 GB)"),
    "tmbud": (os.path.join(DATA, "tmbud"), "300 Timisoara street photos, masks: building, door, window, sky, "
              "vegetation, ground", "no licence stated", "300 labelled photos from github.com/CipiOrhei/TMBuD"),
    "etrims": (os.path.join(DATA, "etrims"), "60 European facades, masks: building, car, door, pavement, road, "
               "sky, vegetation, window", "research use", "ipb.uni-bonn.de/projects/etrims_db (78 MB)"),
    "ade": (os.path.join(DATA, "ade20k"), "ADE20K scene parsing (outdoor photos with buildings kept): "
            "building, sky, vegetation, vehicles, people, ground, poles and signs", "research, non-commercial",
            "data.csail.mit.edu/places/ADEchallenge/ADEChallengeData2016.zip (967 MB)"),
    "openimages": (os.path.join(DATA, "openimages"), "Open Images V5 validation and test photos of buildings, "
                   "houses, towers and skyscrapers with their window and door boxes (no group boxes)",
                   "CC BY 4.0 (annotations), CC BY 2.0 (photos)",
                   "storage.googleapis.com/openimages/v5 tables + open-images-dataset.s3.amazonaws.com photos"),
    "oxford": (os.path.join(DATA, "oxford"), "500 Oxford street views: window, door, balcony, shop, facade "
               "(semantic and instance masks)", "CC BY 4.0",
               "Google Drive 1ASDkxdjPd3xVMeFq9R3HrxtYZIQz_B5s (github.com/sijieaaa/Oxford-RobotCar-Facade)"),
}

# MonuMAI's Spanish labels -> PARTS. Lintelled openings carry no window/door distinction (the teacher
# labels those); the serliana is a tripartite arched opening.
MONUMAI = {
    "arco-medio-punto": "arch", "arco-apuntado": "arch", "arco-herradura": "arch", "arco-conopial": "arch",
    "arco-trilobulado": "arch", "arco-lobulado": "arch", "serliana": "arch",
    "fronton": "pediment", "fronton-partido": "pediment", "fronton-curvo": "pediment_seg",
    "ojo-de-buey": "oculus", "pinaculo-gotico": "finial", "columna-salomonica": "pillar",
    "vano-adintelado": None, "dintel-adovelado": None,
}

# LabelMeFacade colours -> SCENE ("various" and anything else: unlabelled). Windows and doors are
# part of the building.
LABELME = {(128, 0, 0): "building", (0, 0, 128): "building", (128, 128, 0): "building",
           (128, 0, 128): "vehicle", (128, 128, 128): "ground", (128, 64, 0): "ground",
           (0, 128, 128): "sky", (0, 128, 0): "vegetation"}
HZNU_SCENE = {"building": "building", "tree": "vegetation", "car": "vehicle", "sky": "sky"}
COCO_SCENE = {0: "person", 1: "vehicle", 2: "vehicle", 3: "vehicle", 5: "vehicle", 7: "vehicle",
              9: "pole", 11: "pole"}   # traffic light, stop sign
# TMBuD (Timisoara) mask colours in RGB. Its README lists them in BGR (OpenCV); checked on the masks:
# sky (0, 0, 255) on top, building (0, 125, 125) the largest area, windows (255, 255, 0), doors
# (125, 125, 0); "noise" (255, 0, 0), occluders of no given kind low in the frame, stays unlabelled.
TMBUD = {(0, 125, 125): "building", (125, 125, 0): "building", (255, 255, 0): "building", (0, 0, 255): "sky",
         (0, 255, 0): "vegetation", (125, 125, 125): "ground"}
TMBUD_PARTS = {(125, 125, 0): "door", (255, 255, 0): "window"}
# ADE20K (scene parsing, 150 classes): first name of each class in objectInfo150.csv -> SCENE.
ADE_SCENE = {"building": "building", "house": "building", "skyscraper": "building", "tower": "building",
             "sky": "sky", "tree": "vegetation", "plant": "vegetation", "grass": "vegetation", "palm": "vegetation",
             "flower": "vegetation", "car": "vehicle", "bus": "vehicle", "truck": "vehicle", "van": "vehicle",
             "bicycle": "vehicle", "minibike": "vehicle", "person": "person", "road": "ground", "sidewalk": "ground",
             "earth": "ground", "path": "ground", "field": "ground", "dirt track": "ground", "streetlight": "pole",
             "pole": "pole", "signboard": "pole", "traffic light": "pole"}
# Which SCENE classes each source labels; teachers fill the rest (COCO people and vehicles, the
# ADE-trained scene model everything else, poles above all).
SCENE_LABELLED = {"labelme": {"building", "sky", "vegetation", "vehicle", "ground"},
                  "hznu": {"building", "sky", "vegetation", "vehicle"},
                  "tmbud": {"building", "sky", "vegetation", "ground"},
                  "etrims": {"building", "sky", "vegetation", "vehicle", "ground"},
                  "ade": set(SCENE)}
ADE_TEACHER = os.path.join(RUNS, "ade11s", "weights", "best.pt")

# Which PARTS each source labels itself; the teacher fills the other CMP classes.
LABELLED = {"cmp": set(FY.NAMES), "hznu": {"window", "door"}, "cfp": {"window", "door"},
            "tmbud": {"window", "door"}, "etrims": {"window", "door"}, "openimages": {"window", "door"},
            "monumai": {"arch", "pediment", "pediment_seg", "oculus", "finial", "pillar"},
            "oxford": {"window", "door", "balcony", "shop"}}


# ---------------------------------------------------------------- pure helpers (tested)

def box_line(cls, x0, y0, x1, y1):
    """Normalised box -> YOLO 'cls cx cy w h', or None when it is empty after clipping."""
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(1.0, x1), min(1.0, y1)
    if x1 - x0 <= 1e-4 or y1 - y0 <= 1e-4:
        return None
    return "%d %.6f %.6f %.6f %.6f" % (cls, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0)


def poly_line(cls, pts):
    """Normalised polygon [(x, y), ...] -> YOLO-seg 'cls x1 y1 x2 y2 ...', None under 3 points."""
    pts = [(min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)) for x, y in pts]
    if len(pts) < 3:
        return None
    return "%d " % cls + " ".join("%.6f %.6f" % q for q in pts)


def voc_objects(xml_text, mapping=MONUMAI):
    """Pascal VOC annotation -> (width, height, [(class, x0, y0, x1, y1) normalised], unknown labels)."""
    root = ET.fromstring(xml_text)
    w = float(root.findtext("size/width") or 0)
    h = float(root.findtext("size/height") or 0)
    out, unknown = [], []
    for ob in root.findall("object"):
        name = (ob.findtext("name") or "").strip().lower()
        if name not in mapping:
            unknown.append(name)
            continue
        cls = mapping[name]
        bb = ob.find("bndbox")
        if cls is None or bb is None or not w or not h:
            continue
        x0, y0, x1, y1 = (float(bb.findtext(t)) for t in ("xmin", "ymin", "xmax", "ymax"))
        out.append((cls, x0 / w, y0 / h, x1 / w, y1 / h))
    return w, h, out, unknown


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def fill_missing(objs, guesses, labelled, conf=0.5, same=0.5):
    """Adds teacher guesses [(class, conf, x0, y0, x1, y1)] for classes the source does not label,
    above conf and not on top of an object of the same class already there."""
    out = list(objs)
    for k, c, x0, y0, x1, y1 in guesses:
        if k in labelled or c < conf:
            continue
        if any(o[0] == k and iou(o[1:], (x0, y0, x1, y1)) >= same for o in out):
            continue
        out.append((k, x0, y0, x1, y1))
    return out


def mask_polygons(mask, min_frac=0.0005, eps_frac=0.002):
    """Binary mask (H x W, numpy) -> normalised outer polygons of its parts, small specks dropped."""
    import cv2
    import numpy as np
    h, w = mask.shape
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for cnt in contours:
        if cv2.contourArea(cnt) < min_frac * w * h:
            continue
        cnt = cv2.approxPolyDP(cnt, eps_frac * cv2.arcLength(cnt, True), True)
        if len(cnt) >= 3:
            out.append([(float(p[0][0]) / w, float(p[0][1]) / h) for p in cnt])
    return out


def split_ids(ids, seed=7, val=0.1, test=0.1, fixed_test=()):
    """{train, val, test} decided per photo by a hash of its id (plus fixed_test in test): a photo
    keeps its split whatever other photos or sources are added, so a model trained on a larger
    set never trains on an earlier model's test photos."""
    import hashlib
    fixed = set(fixed_test)
    out = {"train": [], "val": [], "test": []}
    for i in ids:
        u = int(hashlib.md5(("%s:%s" % (seed, i)).encode("utf-8")).hexdigest()[:8], 16) / float(16 ** 8)
        out["test" if i in fixed or u < test else "val" if u < test + val else "train"].append(i)
    return dict((k, sorted(v)) for k, v in out.items())


# ---------------------------------------------------------------- sources

def have(name):
    return os.path.isdir(SOURCES[name][0]) and any(os.scandir(SOURCES[name][0]))


def sources():
    for name, (path, what, lic, dl) in SOURCES.items():
        print("%-8s %-8s %s\n         licence: %s | %s" % (name, "ok" if have(name) else "MISSING", what, lic,
                                                            dl if not have(name) else path))
    for label, path in [("teacher", t) for t, _ in TEACHERS] + [("seg COCO", SEG_WEIGHTS)]:
        print("%-8s %-8s %s" % (label, "ok" if os.path.exists(path) else "MISSING", path))


def download(names):
    for name in names:
        if name == "monumai":
            if not have("monumai"):
                subprocess.check_call(["git", "clone", "--depth", "1", "https://github.com/ari-dasci/OD-MonuMAI",
                                       SOURCES["monumai"][0]])
        elif name == "oxford":
            out = SOURCES["oxford"][0]
            os.makedirs(out, exist_ok=True)
            zpath = os.path.join(out, "oxford.zip")
            if not os.path.exists(zpath):
                try:
                    import gdown
                except ImportError:
                    sys.exit("pip install gdown in this environment first (Google Drive download)")
                gdown.download(id="1ASDkxdjPd3xVMeFq9R3HrxtYZIQz_B5s", output=zpath, quiet=False)
            shutil.unpack_archive(zpath, out)
        elif name == "openimages":
            download_openimages()
        elif name == "styles":
            download_style()
        elif name in ("weights-m", "cls-weights"):
            import urllib.request
            f = "yolo11m.pt" if name == "weights-m" else "yolo11s-cls.pt"
            if not os.path.exists(os.path.join(RUNS, f)):
                urllib.request.urlretrieve("https://github.com/ultralytics/assets/releases/download/v8.3.0/" + f,
                                           os.path.join(RUNS, f))
        elif name == "seg-weights":
            if not os.path.exists(SEG_WEIGHTS):
                import urllib.request
                urllib.request.urlretrieve(
                    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s-seg.pt", SEG_WEIGHTS)
        else:
            sys.exit("unknown download: %s" % name)
        print("%s: done" % name)


def _models():
    os.environ.setdefault("YOLO_OFFLINE", "1")
    os.environ.setdefault("YOLO_CONFIG_DIR", CFG)
    from ultralytics import YOLO
    return YOLO


def _write(out, split, fid, src, lines):
    FY._copy_small(src, os.path.join(out, "images", split, fid + ".jpg"))
    with open(os.path.join(out, "labels", split, fid + ".txt"), "w") as fh:
        fh.write("\n".join(lines) + ("\n" if lines else ""))


def _fresh(out):
    if os.path.isdir(out):
        shutil.rmtree(out)
    for s in ("train", "val", "test"):
        os.makedirs(os.path.join(out, "images", s))
        os.makedirs(os.path.join(out, "labels", s))


def _yaml(out, name, names, task="detect"):
    with open(os.path.join(out, name), "w") as fh:
        fh.write("# task: %s\n" % task)
        fh.write("path: %s\ntrain: images/train\nval: images/val\ntest: images/test\nnames:\n" % out.replace("\\", "/"))
        for i, n in enumerate(names):
            fh.write("  %d: %s\n" % (i, n))


def _limit(ids, limit):
    return ids[:limit] if limit else ids


# ---------------------------------------------------------------- scene dataset

def rgb_polys(path, palette):
    """Colour mask -> [(class, normalised polygon)] for every colour of palette."""
    import numpy as np
    from PIL import Image
    lab = np.array(Image.open(path).convert("RGB"))
    return [(k, poly) for rgb, k in palette.items() for poly in mask_polygons(np.all(lab == rgb, axis=-1))]


def index_polys(path, mapping):
    """Class-index mask -> [(class, normalised polygon)], indices grouped by the class they map to."""
    import numpy as np
    from PIL import Image
    lab = np.array(Image.open(path))
    if lab.ndim == 3:
        lab = lab[..., 0]
    out = []
    for k in sorted(set(mapping.values())):
        m = np.isin(lab, [i for i, c in mapping.items() if c == k])
        out += [(k, poly) for poly in mask_polygons(m)]
    return out


def _hznu_polys(fid, img):
    from PIL import Image
    with open(os.path.join(FY.HZNU, fid + ".json"), encoding="utf-8") as fh:
        data = json.load(fh)
    with Image.open(img) as im:
        w, h = im.size
    out = []
    for sh in data.get("shapes", []):
        k = HZNU_SCENE.get(sh.get("label"))
        pts = sh.get("points") or []
        if k and len(pts) >= 3:
            out.append((k, [(float(x) / w, float(y) / h) for x, y in pts]))
    return out


def ade_classes(text):
    """objectInfo150.txt (tab-separated: Idx, Ratio, Train, Val, Name with comma-separated synonyms)
    -> {class index: SCENE class} by each class's first name."""
    out = {}
    for line in text.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 5 and cols[0].strip().isdigit():
            first = cols[-1].split(",")[0].strip().lower()
            if first in ADE_SCENE:
                out[int(cols[0])] = ADE_SCENE[first]
    return out


def _ade_root():
    for dirpath, dirs, files in os.walk(SOURCES["ade"][0]):
        if "objectInfo150.txt" in files:
            return dirpath
    return None


def _ade_items(limit, min_building=0.08):
    """ADE20K outdoor photos where buildings cover at least min_building of the frame."""
    import numpy as np
    from PIL import Image
    root = _ade_root()
    if root is None:
        return []
    with open(os.path.join(root, "objectInfo150.txt"), encoding="utf-8") as fh:
        mapping = ade_classes(fh.read())
    building = [i for i, c in mapping.items() if c == "building"]
    items = []
    for part in ("training", "validation"):
        adir = os.path.join(root, "annotations", part)
        for f in sorted(os.listdir(adir)) if os.path.isdir(adir) else []:
            path = os.path.join(adir, f)
            if np.isin(np.array(Image.open(path)), building).mean() < min_building:
                continue
            img = os.path.join(root, "images", part, f[:-4] + ".jpg")
            items.append(("ade_" + f[:-4], "ade", img, lambda path=path: index_polys(path, mapping)))
            if limit and len(items) >= limit:
                return items
    return items


def _tmbud_items(limit):
    root = SOURCES["tmbud"][0]
    items = []
    ldir = os.path.join(root, "gt_label")
    for f in sorted(os.listdir(ldir)) if os.path.isdir(ldir) else []:
        stem = f[:-4]
        img = next((os.path.join(root, "images", stem + e) for e in (".jpg", ".png", ".JPG")
                    if os.path.exists(os.path.join(root, "images", stem + e))), None)
        if img:
            items.append(("tm_" + stem, "tmbud", img, os.path.join(ldir, f)))
    return _limit(items, limit)


# eTRIMS 8-class index masks: classes in alphabetical order after the background.
ETRIMS_NAMES = ["background", "building", "car", "door", "pavement", "road", "sky", "vegetation", "window"]
ETRIMS_SCENE = {1: "building", 2: "vehicle", 3: "building", 4: "ground", 5: "ground", 6: "sky", 7: "vegetation",
                8: "building"}
ETRIMS_PARTS = {3: "door", 8: "window"}


def _etrims_items(limit, objects=False):
    """eTRIMS 8-class set (indices 0-8, alphabetical after the background; checked: sky on top,
    road at the bottom, cars in 27 photos): images/08_etrims-ds with the semantic masks of
    annotations/08_etrims-ds, or with objects=True also the instance masks of
    annotations-object/08_etrims-ds -> (id, source, image, semantic, instances)."""
    base = os.path.join(SOURCES["etrims"][0], "etrims-db_v1")
    sem_dir, obj_dir = os.path.join(base, "annotations", "08_etrims-ds"), os.path.join(base, "annotations-object", "08_etrims-ds")
    img_dir = os.path.join(base, "images", "08_etrims-ds")
    items = []
    for f in sorted(os.listdir(sem_dir)) if os.path.isdir(sem_dir) else []:
        stem = f[:-4]
        img = os.path.join(img_dir, stem + ".jpg")
        if os.path.exists(img):
            items.append(("et_" + stem, "etrims", img, os.path.join(sem_dir, f), os.path.join(obj_dir, f)))
    return _limit(items, limit)


def scene_items(limit=0, sources=None):
    """[(id, source, image, loader)]: loader() -> [(SCENE class, polygon)] from the source's labels."""
    want = lambda name: (sources is None or name in sources) and have(name)
    items = []
    if want("labelme"):
        root = SOURCES["labelme"][0]
        for f in _limit(sorted(os.listdir(os.path.join(root, "labels"))), limit):
            path = os.path.join(root, "labels", f)
            items.append(("lm_" + f[:-4], "labelme", os.path.join(root, "images", f[:-4] + ".jpg"),
                          lambda path=path: rgb_polys(path, LABELME)))
    if sources is None or "hznu" in sources:
        for fid in _limit(FY.hznu_ids(), limit):
            img = os.path.join(FY.HZNU, fid + ".jpg")
            items.append(("hz_" + fid, "hznu", img, lambda fid=fid, img=img: _hznu_polys(fid, img)))
    if want("tmbud"):
        items += [(i, s, img, lambda m=m: rgb_polys(m, TMBUD)) for i, s, img, m in _tmbud_items(limit)]
    if want("etrims"):
        items += [(i, s, img, lambda m=m: index_polys(m, ETRIMS_SCENE)) for i, s, img, m, _ in _etrims_items(limit)]
    if want("ade"):
        items += _ade_items(limit)
    return items


def scene(limit=0, sources=None, name="scene", teacher=True):
    """YOLO-seg dataset data/yolo-NAME from the scene sources; missing classes filled by teachers."""
    out = os.path.join(DATA, "yolo-%s" % name)
    _fresh(out)
    items = scene_items(limit, sources)
    test_fixed = ["hz_" + i for i in FY.test_ids(hznu=True) if not FB.ID_RE.match(i)]
    split = split_ids([i[0] for i in items], fixed_test=test_fixed)
    where = dict((fid, s) for s, ids in split.items() for fid in ids)
    teachers = []
    for path, classes, names in ((SEG_WEIGHTS, {"person", "vehicle"}, COCO_SCENE),
                                 (ADE_TEACHER, set(SCENE) - {"person", "vehicle"}, None)):
        if teacher and os.path.exists(path):
            model = _models()(path)
            teachers.append((model, classes, names or dict((i, n) for i, n in model.names.items() if n in SCENE)))
        elif teacher:
            print("no teacher at %s: %s stay unlabelled where a source lacks them" % (path, ", ".join(sorted(classes))))
    counts = dict((k, 0) for k in SCENE)
    filled = 0
    for fid, src, img, loader in items:
        if not os.path.exists(img):
            continue
        polys = loader()
        missing = set(SCENE) - SCENE_LABELLED[src]
        for model, classes, names in teachers:
            todo = classes & missing
            if not todo:
                continue
            for r in model.predict(img, imgsz=1024, conf=0.4, verbose=False):
                if r.masks is None:
                    continue
                for cls, poly in zip(r.boxes.cls.tolist(), r.masks.xyn):
                    k = names.get(int(cls))
                    if k in todo and len(poly) >= 3:
                        polys.append((k, [(float(x), float(y)) for x, y in poly]))
                        filled += 1
        lines = [ln for ln in (poly_line(SCENE.index(k), p) for k, p in polys) if ln]
        for k, _ in polys:
            counts[k] += 1
        _write(out, where[fid], fid, img, lines)
    _yaml(out, "%s.yaml" % name, SCENE, task="segment")
    print(json.dumps({"images": dict((s, len(v)) for s, v in split.items()), "teacher_polygons": filled,
                      "polygons": counts}))


# ---------------------------------------------------------------- parts dataset

def _monumai_items(limit):
    root = SOURCES["monumai"][0]
    items, unknown = [], set()
    for dirpath, _, files in os.walk(root):
        for f in sorted(files):
            if not f.endswith(".xml"):
                continue
            with open(os.path.join(dirpath, f), encoding="utf-8", errors="replace") as fh:
                _, _, objs, unk = voc_objects(fh.read())
            unknown.update(unk)
            style_dir = os.path.dirname(dirpath)
            img = next((os.path.join(d, f[:-4] + e) for d in (style_dir, dirpath) for e in (".jpg", ".JPG", ".jpeg")
                        if os.path.exists(os.path.join(d, f[:-4] + e))), None)
            if img:
                items.append(("mm_" + re.sub(r"\W", "_", os.path.basename(style_dir) + "_" + f[:-4]), img, objs))
    if unknown:
        print("MonuMAI labels not mapped (ignored): %s" % ", ".join(sorted(unknown)))
    return _limit(items, limit)


OXFORD = {(255, 0, 0): "window", (255, 128, 0): "door", (128, 0, 255): "balcony", (0, 255, 0): "shop"}


def instance_boxes(sem, inst, palette=OXFORD):
    """Oxford masks (H x W x 3 arrays): every instance colour of inst becomes a normalised box whose
    class is the most common semantic colour under it; instances of other classes (the facade)
    are skipped. Only windows have instances in the data: doors, balconies and shops are the
    connected parts of their semantic colour."""
    import numpy as np
    h, w = inst.shape[:2]
    ids = inst[..., 0].astype(np.int64) << 16 | inst[..., 1].astype(np.int64) << 8 | inst[..., 2]
    sem_ids = sem[..., 0].astype(np.int64) << 16 | sem[..., 1].astype(np.int64) << 8 | sem[..., 2]
    key = dict(((r << 16 | g << 8 | b), k) for (r, g, b), k in palette.items())
    out = []
    for iid in np.unique(ids):
        if iid == 0:
            continue
        ys, xs = np.nonzero(ids == iid)
        vals, counts = np.unique(sem_ids[ys, xs], return_counts=True)
        k = key.get(int(vals[np.argmax(counts)]))
        if k:
            out.append((k, xs.min() / float(w), ys.min() / float(h), (xs.max() + 1) / float(w), (ys.max() + 1) / float(h)))
    import cv2
    free = ids == 0
    for rgb, k in palette.items():
        m = free & (sem_ids == (rgb[0] << 16 | rgb[1] << 8 | rgb[2]))
        if not m.any():
            continue
        n, _, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)
        for x, y, bw, bh, area in stats[1:]:
            if area >= 0.0002 * w * h:
                out.append((k, x / float(w), y / float(h), (x + bw) / float(w), (y + bh) / float(h)))
    return out


def _oxford_items(limit):
    """Oxford RobotCar Facade: {train,test}/images_N/*.png with labels_N_semantic and
    labels_N_instance of the same name."""
    import numpy as np
    from PIL import Image
    root = SOURCES["oxford"][0]
    items = []
    for part in ("train", "test"):
        base = os.path.join(root, part)
        if not os.path.isdir(base):
            continue
        dirs = dict((d.split("_")[-1] if d.startswith("labels") else "images", os.path.join(base, d))
                    for d in os.listdir(base))
        if not all(k in dirs for k in ("images", "semantic", "instance")):
            continue
        for f in sorted(os.listdir(dirs["images"])):
            sem = np.array(Image.open(os.path.join(dirs["semantic"], f)).convert("RGB"))
            inst = np.array(Image.open(os.path.join(dirs["instance"], f)).convert("RGB"))
            items.append(("ox_" + f.rsplit(".", 1)[0], os.path.join(dirs["images"], f), instance_boxes(sem, inst)))
            if limit and len(items) >= limit:
                return items
    return items


OI_CLASSES = {"/m/0d4v4": "window", "/m/02dgv": "door", "/m/0cgh4": "building", "/m/079cl": "skyscraper",
              "/m/03jm5": "house", "/m/01fdzj": "tower"}


def openimages_select(tables):
    """{split/id: [(window|door, x0, y0, x1, y1)]} for photos with a building (house, tower,
    skyscraper) and window or door boxes, none of them a group box (a box around a row of windows
    would leave the windows inside unlabelled)."""
    import csv
    boxes, kinds, grouped = {}, {}, set()
    for split, path in tables:
        with open(path, newline="") as fh:
            for r in csv.DictReader(fh):
                k = OI_CLASSES.get(r["LabelName"])
                if not k:
                    continue
                key = "%s/%s" % (split, r["ImageID"])
                kinds.setdefault(key, set()).add(k)
                if k in ("window", "door"):
                    if r.get("IsGroupOf") == "1":
                        grouped.add(key)
                    boxes.setdefault(key, []).append((k, float(r["XMin"]), float(r["YMin"]), float(r["XMax"]), float(r["YMax"])))
    return dict((k, v) for k, v in boxes.items()
                if k not in grouped and kinds[k] & {"building", "skyscraper", "house", "tower"})


def download_openimages(threads=8):
    import concurrent.futures as cf
    import urllib.request
    root = SOURCES["openimages"][0]
    os.makedirs(os.path.join(root, "images"), exist_ok=True)
    tables = []
    for split in ("validation", "test"):
        path = os.path.join(root, "%s-annotations-bbox.csv" % split)
        if not os.path.exists(path):
            urllib.request.urlretrieve("https://storage.googleapis.com/openimages/v5/%s-annotations-bbox.csv" % split, path)
        tables.append((split, path))
    sel = openimages_select(tables)
    with open(os.path.join(root, "facades.json"), "w") as fh:
        json.dump(sel, fh)

    def get(key):
        dst = os.path.join(root, "images", key.replace("/", "_") + ".jpg")
        if not os.path.exists(dst):
            urllib.request.urlretrieve("https://open-images-dataset.s3.amazonaws.com/%s.jpg" % key, dst + ".part")
            os.replace(dst + ".part", dst)
        return key

    with cf.ThreadPoolExecutor(threads) as ex:
        n = sum(1 for _ in ex.map(get, sorted(sel)))
    print("openimages: %d photos" % n)


def _openimages_items(limit):
    root = SOURCES["openimages"][0]
    path = os.path.join(root, "facades.json")
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        sel = json.load(fh)
    items = []
    for key in sorted(sel):
        img = os.path.join(root, "images", key.replace("/", "_") + ".jpg")
        if os.path.exists(img):
            items.append(("oi_" + key.split("/")[-1], "openimages", img, [tuple(b) for b in sel[key]]))
    return _limit(items, limit)


def _parts_masks(limit):
    """TMBuD (colour masks; adjacent windows may merge) and eTRIMS (instance masks) -> boxes."""
    import numpy as np
    from PIL import Image
    items = []
    if have("tmbud"):
        for fid, src, img, m in _tmbud_items(limit):
            sem = np.array(Image.open(m).convert("RGB"))
            items.append((fid, src, img, instance_boxes(sem, np.zeros_like(sem), TMBUD_PARTS)))
    if have("etrims"):
        palette = dict(((i, 0, 0), k) for i, k in ETRIMS_PARTS.items())
        for fid, src, img, sem_path, obj_path in _etrims_items(limit, objects=True):
            as_rgb = lambda a: np.stack([a, np.zeros_like(a), np.zeros_like(a)], axis=-1).astype(np.uint8)
            sem = as_rgb(np.array(Image.open(sem_path)))
            inst = as_rgb(np.array(Image.open(obj_path))) if os.path.exists(obj_path) else np.zeros_like(sem)
            items.append((fid, src, img, instance_boxes(sem, inst, palette)))
    return items


def parts(limit=0, teacher=True, sources=None, name="parts"):
    out = os.path.join(DATA, "yolo-%s" % name)
    _fresh(out)
    items = []   # (id, source, image, objs)
    test_cmp = [i for i in FY.test_ids(hznu=True)]
    for fid in _limit(FB.all_ids(), limit):
        _, objs = FB.read_annotation(fid)
        items.append((fid, "cmp", FB._paths(fid) + ".jpg", objs))
    for fid in _limit(FY.hznu_ids(), limit):
        items.append((fid, "hznu", os.path.join(FY.HZNU, fid + ".jpg"), FY.hznu_objs(fid)))
    for fid, base in _limit(sorted(FY.cfp_entries().items()), limit):
        items.append((fid, "cfp", FY._image(base), FY.labelme_objs(base + ".json", FY._image(base))))
    if have("monumai"):
        items += [(fid, "monumai", img, objs) for fid, img, objs in _monumai_items(limit)]
    if have("oxford"):
        items += [(fid, "oxford", img, objs) for fid, img, objs in _oxford_items(limit)]
    items += [(fid, src, img, objs) for fid, src, img, objs in _parts_masks(limit)]
    if sources is None or "openimages" in sources:
        items += _openimages_items(limit)
    split = split_ids([i[0] for i in items], fixed_test=test_cmp)   # over every source: a subset keeps it
    if sources:
        items = [i for i in items if i[1] in sources]
        keep = set(i[0] for i in items)
        split = dict((s, [f for f in ids if f in keep]) for s, ids in split.items())
    where = dict((fid, s) for s, ids in split.items() for fid in ids)
    models = []
    for path, classes in (TEACHERS if teacher else []):
        if os.path.exists(path):
            models.append((_models()(path), classes))
        else:
            print("no teacher at %s: %s stay unlabelled where missing" % (path, ", ".join(sorted(classes))))
    counts = dict((k, 0) for k in PARTS)
    added = 0
    for fid, src, img, objs in items:
        if not os.path.exists(img):
            continue
        if models:
            guesses = []
            for model, classes in models:
                if classes <= LABELLED[src]:
                    continue
                for r in model.predict(img, imgsz=1024, conf=0.5, verbose=False):
                    for c, conf, b in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(), r.boxes.xyxyn.tolist()):
                        if model.names[int(c)] in classes:
                            guesses.append((model.names[int(c)], conf, b[0], b[1], b[2], b[3]))
            before = len(objs)
            objs = fill_missing(objs, guesses, LABELLED[src])
            added += len(objs) - before
        lines = [ln for ln in (box_line(PARTS.index(k), x0, y0, x1, y1) for k, x0, y0, x1, y1 in objs if k in PARTS) if ln]
        for k, *_ in objs:
            if k in counts:
                counts[k] += 1
        _write(out, where[fid], fid, img, lines)
    _yaml(out, "%s.yaml" % name, PARTS)
    print(json.dumps({"images": dict((s, len(v)) for s, v in split.items()), "teacher_boxes": added, "boxes": counts}))


# ---------------------------------------------------------------- training

def train(kind, epochs=120, batch=8, imgsz=1024, model=None, hours=None, run=None):
    """Trains on data/yolo-KIND into data/det-runs/RUN (default KIND11s) and lists there, in
    seen.txt, every photo it trains or validates on: reports keep those out of their tests."""
    root = os.path.join(DATA, "yolo-%s" % kind)
    run = run or "%s11s" % kind
    if kind == "style":
        return train_style(epochs, batch, model, hours, run)
    data = os.path.join(root, "%s.yaml" % kind)
    if not os.path.exists(data):
        sys.exit("build the dataset first: python tools/train_data.py %s" % kind)
    _write_seen(root, run)
    with open(data) as fh:
        seg = fh.readline().strip() == "# task: segment"
    weights = model or (SEG_WEIGHTS if seg else os.path.join(RUNS, "yolo11s.pt"))
    if not os.path.exists(weights):
        sys.exit("no starting weights at %s (run: download seg-weights)" % weights)
    YOLO = _models()
    extra = {"time": hours} if hours else {}   # a cap in hours: training stops by then whatever the epoch
    YOLO(weights).train(data=data, epochs=epochs, imgsz=imgsz, batch=batch, workers=2, patience=30,
                        plots=False, project=RUNS, name=run, exist_ok=True, **extra)


def _write_seen(root, run, splits=("train", "val")):
    os.makedirs(os.path.join(RUNS, run), exist_ok=True)
    stems = []
    for sp in splits:
        d = os.path.join(root, "images", sp)
        if os.path.isdir(d):
            stems += [f.rsplit(".", 1)[0] for f in os.listdir(d)]
        d = os.path.join(root, sp)   # classification layout: SPLIT/CLASS/photo
        if os.path.isdir(d):
            stems += [f.rsplit(".", 1)[0] for c in os.listdir(d) for f in os.listdir(os.path.join(d, c))]
    with open(os.path.join(RUNS, run, "seen.txt"), "w") as fh:
        fh.write("\n".join(sorted(stems)) + "\n")


# ---------------------------------------------------------------- style classifier

STYLE_URL = "https://vision.csi.miamioh.edu/data/FacadeStyleDataset/"
# The builder's style per architectural style (the classifier keeps all 25; this is how a reading
# turns one into spec style). Anything not listed is plain.
STYLE_TO_SPEC = {"classic": ("Baroque", "Beaux-Arts", "Georgian", "Edwardian", "Colonial", "Palladian", "Queen Anne",
                             "Romanesque", "Gothic", "Renaissance", "Greek Revival", "Tudor Revival", "Byzantine",
                             "Art Nouveau", "Russian Revival", "Novelty"),
                 "modern": ("Bauhaus", "International style", "Deconstructivism", "Postmodern", "Chicago school",
                            "Art Deco", "American Foursquare", "American craftsman")}


def spec_style(style):
    """Architectural style name -> the builder's style (classic, modern or plain)."""
    for k, names in STYLE_TO_SPEC.items():
        if any(style.lower().startswith(n.lower()) for n in names):
            return k
    return "plain"


def _fetch(url, dst=None, tries=4, timeout=60):
    """GET with retries and a growing pause; to dst through a .part file (no truncated photos)."""
    import urllib.request
    for i in range(tries):
        try:
            data = urllib.request.urlopen(url, timeout=timeout).read()
            if dst is None:
                return data
            with open(dst + ".part", "wb") as fh:
                fh.write(data)
            os.replace(dst + ".part", dst)
            return True
        except Exception:
            if i == tries - 1:
                return None
            time.sleep(5 * (i + 1))


def download_style(threads=3):
    """The 25-style facade set (Xu et al., ECCV 2014; Wikimedia Commons photos), folder by folder.
    Gentle on the university server: few connections, retries; files that keep failing are skipped
    and fetched by the next run."""
    import concurrent.futures as cf
    import urllib.parse
    out = os.path.join(DATA, "styles")

    def links(url):
        page = _fetch(url)
        if page is None:
            return []
        return [urllib.parse.unquote(h) for h in re.findall(r'href="([^"?/][^"]*)"', page.decode("utf-8", "replace"))]

    jobs = []
    for d in links(STYLE_URL):
        if d.endswith("/"):
            for f in links(STYLE_URL + urllib.parse.quote(d)):
                if f.lower().endswith((".jpg", ".jpeg", ".png")):
                    jobs.append((d.rstrip("/"), f))

    def get(job):
        d, f = job
        dst = os.path.join(out, d, f)
        if os.path.exists(dst):
            return True
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        return bool(_fetch(STYLE_URL + urllib.parse.quote(d + "/" + f), dst))

    with cf.ThreadPoolExecutor(threads) as ex:
        ok = list(ex.map(get, jobs))
    print("styles: %d of %d photos in %d styles (%d failed, run again to retry)"
          % (sum(ok), len(jobs), len(set(d for d, _ in jobs)), len(ok) - sum(ok)))


def style_dataset():
    """data/yolo-style/{train,val,test}/<style>/photo.jpg (Ultralytics classification layout)."""
    src = os.path.join(DATA, "styles")
    out = os.path.join(DATA, "yolo-style")
    if os.path.isdir(out):
        shutil.rmtree(out)
    items = [(c, f) for c in sorted(os.listdir(src)) if os.path.isdir(os.path.join(src, c))
             for f in sorted(os.listdir(os.path.join(src, c)))]
    split = split_ids(["%s/%s" % cf for cf in items])
    where = dict((i, s) for s, ids in split.items() for i in ids)
    for c, f in items:
        dst = os.path.join(out, where["%s/%s" % (c, f)], c.replace(" ", "_"), re.sub(r"[^\w.-]", "_", f))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            FY._copy_small(os.path.join(src, c, f), dst, side=640)
        except Exception as e:   # a few Wikimedia files are not readable images
            print("skipped %s/%s: %s" % (c, f, e))
    print(json.dumps(dict((s, len(v)) for s, v in split.items())))


def train_style(epochs, batch, model, hours, run):
    root = os.path.join(DATA, "yolo-style")
    if not os.path.isdir(root):
        sys.exit("build the dataset first: python tools/train_data.py style")
    _write_seen(root, run)
    weights = model or os.path.join(RUNS, "yolo11s-cls.pt")
    extra = {"time": hours} if hours else {}
    _models()(weights).train(data=root, epochs=epochs, imgsz=320, batch=max(batch, 32), workers=2, patience=20,
                             plots=False, project=RUNS, name=run, exist_ok=True, **extra)


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("sources")
    d = sub.add_parser("download")
    d.add_argument("names", nargs="+", choices=["monumai", "oxford", "seg-weights", "styles", "weights-m", "cls-weights",
                                               "openimages"])
    s = sub.add_parser("scene")
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--no-teacher", action="store_true")
    s.add_argument("--sources", nargs="+", choices=["labelme", "hznu", "tmbud", "etrims", "ade"])
    s.add_argument("--name", default="scene", help="dataset folder data/yolo-NAME and run NAME11s")
    p = sub.add_parser("parts")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--no-teacher", action="store_true")
    p.add_argument("--sources", nargs="+", choices=["cmp", "hznu", "cfp", "monumai", "oxford", "tmbud", "etrims",
                                                     "openimages"])
    p.add_argument("--name", default="parts", help="dataset folder data/yolo-NAME and run NAME11s")
    sub.add_parser("style")
    t = sub.add_parser("train")
    t.add_argument("kind", help="scene, parts, or the NAME of a parts dataset (e.g. monumai)")
    t.add_argument("--epochs", type=int, default=120)
    t.add_argument("--batch", type=int, default=8)
    t.add_argument("--imgsz", type=int, default=1024)
    t.add_argument("--model")
    t.add_argument("--hours", type=float, help="stop after this many hours (Ultralytics time)")
    t.add_argument("--run", help="run folder under data/det-runs (default KIND11s)")
    a = ap.parse_args(argv[1:])
    if a.cmd == "sources":
        sources()
    elif a.cmd == "download":
        download(a.names)
    elif a.cmd == "scene":
        scene(a.limit, a.sources, a.name, not a.no_teacher)
    elif a.cmd == "style":
        style_dataset()
    elif a.cmd == "parts":
        parts(a.limit, not a.no_teacher, a.sources, a.name)
    else:
        train(a.kind, a.epochs, a.batch, a.imgsz, a.model, a.hours, a.run)


if __name__ == "__main__":
    main(sys.argv)
