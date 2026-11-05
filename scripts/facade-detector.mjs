// detect_facade: runs the local facade detector (YOLO trained on facade datasets, see
// tools/facade_yolo.py) on a photo and returns a px facade draft for the model to correct.
// It is offered only when a Python with ultralytics and trained weights are present:
//   RHINO_FACADE_PYTHON   python executable (default data/venv-det in this repo)
//   RHINO_FACADE_WEIGHTS  weights file      (default data/det-runs/parts11s/weights/best.pt, the parts
//                         model with arches, oculi, pediments and finials; else all11s)
// The image path is the only model input: it must be an existing image file, and it travels as
// one argv entry to a fixed script (no shell), with a timeout and an output cap.
import { execFile } from "node:child_process";
import { existsSync, statSync, realpathSync } from "node:fs";
import { extname, isAbsolute, join } from "node:path";

export const IMAGE_EXT = new Set([".jpg", ".jpeg", ".png", ".webp", ".bmp"]);
export const MAX_IMAGE_BYTES = 50 * 1024 * 1024;
const TIMEOUT_MS = 120_000;
const MAX_OUTPUT = 2 * 1024 * 1024;

export const DETECT_TOOL = {
  name: "detect_facade",
  description:
    "Local facade detector: reads a facade photo (absolute path) and returns a px facade draft {img:[w,h], els:[{k, box}]} " +
    "in that image's pixels, found by a model trained on facade datasets. Call it before reading a facade photo; then " +
    "correct the draft (doors, shops, pillars, h, the facade's px corners) instead of reading every element. " +
    "Measured: about 0.62 IoU per element against 0.52 for an unaided reading.",
  inputSchema: {
    type: "object",
    properties: {
      image: { type: "string", description: "Absolute path of the photo (jpg, png, webp, bmp)." },
      conf: { type: "number", description: "Optional confidence threshold, 0.05-0.95 (default 0.25)." },
    },
    required: ["image"],
  },
};

export function findDetector(repoRoot, env = process.env) {
  const python = env.RHINO_FACADE_PYTHON ||
    join(repoRoot, "data", "venv-det", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const run = (name) => join(repoRoot, "data", "det-runs", name, "weights", "best.pt");
  const weights = env.RHINO_FACADE_WEIGHTS || [run("parts11s"), run("all11s")].find((p) => existsSync(p)) || run("all11s");
  const script = join(repoRoot, "tools", "facade_yolo.py");
  if (![python, weights, script].every((p) => existsSync(p))) return null;
  const cfg = join(repoRoot, "data", "det-runs", "cfg");
  return { python, weights, script, configDir: existsSync(cfg) ? cfg : null };
}

// Returns the resolved image path, or throws with a short reason.
export function checkImage(path) {
  if (typeof path !== "string" || !path || path.length > 1024 || path.includes("\0")) throw new Error("image must be a path");
  if (!isAbsolute(path)) throw new Error("image path must be absolute");
  if (!IMAGE_EXT.has(extname(path).toLowerCase())) throw new Error("image must be jpg, png, webp or bmp");
  let real;
  try { real = realpathSync(path); } catch { throw new Error("image not found"); }
  if (!IMAGE_EXT.has(extname(real).toLowerCase())) throw new Error("image must be jpg, png, webp or bmp");
  const st = statSync(real);
  if (!st.isFile()) throw new Error("image is not a file");
  if (st.size > MAX_IMAGE_BYTES) throw new Error("image larger than 50 MB");
  return real;
}

export function checkConf(conf) {
  if (conf === undefined) return 0.25;
  if (typeof conf !== "number" || !Number.isFinite(conf) || conf < 0.05 || conf > 0.95) throw new Error("conf must be 0.05-0.95");
  return conf;
}

// Resolves with the draft's JSON text; rejects with a short message.
export function runDetector(det, image, conf, run = execFile) {
  const env = { ...process.env };
  if (det.configDir) env.YOLO_CONFIG_DIR = det.configDir;
  return new Promise((resolve, reject) => {
    run(det.python, ["-I", det.script, "detect-image", image, det.weights, String(conf)],
      { timeout: TIMEOUT_MS, maxBuffer: MAX_OUTPUT, windowsHide: true, env, shell: false },
      (err, stdout) => {
        if (err) return reject(new Error(err.killed ? "detector timed out" : "detector failed"));
        const line = String(stdout).trim().split(/\r?\n/).pop() ?? "";
        try {
          const out = JSON.parse(line);
          if (!Array.isArray(out?.els) || !Array.isArray(out?.img)) throw new Error();
          resolve(JSON.stringify(out));
        } catch { reject(new Error("detector returned no draft")); }
      });
  });
}
