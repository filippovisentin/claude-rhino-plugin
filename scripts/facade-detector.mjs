// detect_facade: runs the local facade detector (YOLO trained on facade datasets, see
// tools/facade_yolo.py) on a photo and returns a px facade draft for the model to correct.
// It is offered only when a Python with ultralytics and trained weights are present:
//   RHINO_FACADE_PYTHON   python executable (default data/venv-det in this repo)
//   RHINO_FACADE_WEIGHTS  weights file, or several joined by the path delimiter (";" on Windows) to fuse
//                         their boxes, the first counting double (default: parts2m fused with parts11s,
//                         the parts models with arches, oculi, pediments and finials; else the best
//                         single run of parts2m, parts11s, all11s)
// The image path is the only model input: it must be an existing image file, and it travels as
// one argv entry to a fixed script (no shell), with a timeout and an output cap.
import { execFile } from "node:child_process";
import { existsSync, statSync, realpathSync } from "node:fs";
import { delimiter, extname, isAbsolute, join } from "node:path";
import { installedDetector } from "./detector-install.mjs";

export const IMAGE_EXT = new Set([".jpg", ".jpeg", ".png", ".webp", ".bmp"]);
export const MAX_IMAGE_BYTES = 50 * 1024 * 1024;
const TIMEOUT_MS = 120_000;
const MAX_OUTPUT = 2 * 1024 * 1024;
// Best first. Report of 2026-11-06 (unseen photos, mAP50): parts2m 0.764 CMP / 0.982 modern / 0.834 Oxford,
// parts11s 0.756 / 0.976 / 0.721, all11s 0.761 / 0.981 / 0.324 and no arches, pediments or finials.
export const DEFAULT_RUNS = ["parts2m", "parts11s", "all11s"];
// Fused when both are trained (tools/ensemble_report.py, same photos): CMP mAP50 0.742 -> 0.764 and pixel
// IoU 0.619 -> 0.629 over parts2m alone, Oxford 0.813 -> 0.807, monuments 0.988 -> 0.999.
export const FUSED_RUNS = ["parts2m", "parts11s"];

export const DETECT_TOOL = {
  name: "detect_facade",
  description:
    "Local facade detector: reads a facade photo (absolute path) and returns a px facade draft {img:[w,h], px, els:[{k, box}]} " +
    "in that image's pixels, found by a model trained on facade datasets. Call it before reading a facade photo; then " +
    "correct the draft (doors, shops, pillars, h, and px: proposed as the box around the elements) instead of reading every element. " +
    "Measured: about 0.63 IoU per element against 0.52 for an unaided reading.",
  inputSchema: {
    type: "object",
    properties: {
      image: { type: "string", description: "Absolute path of the photo (jpg, png, webp, bmp)." },
      conf: { type: "number", description: "Optional confidence threshold, 0.05-0.95 (default 0.25)." },
    },
    required: ["image"],
  },
};

// Where the detector comes from, first complete one wins: RHINO_FACADE_PYTHON / RHINO_FACADE_WEIGHTS
// (source "env"), the install made by scripts/setup.mjs under %LOCALAPPDATA%\claude-rhino
// ("installed", only when its setup.json matches models.json), the repo's data/ folder ("repo").
export function findDetector(repoRoot, env = process.env) {
  const custom = Boolean(env.RHINO_FACADE_PYTHON || env.RHINO_FACADE_WEIGHTS);
  if (!custom) {
    const inst = installedDetector(repoRoot, env);
    const script = join(repoRoot, "tools", "facade_yolo.py");
    if (inst && existsSync(script)) return { ...inst, script, source: "installed" };
  }
  const det = findRepoDetector(repoRoot, env);
  return det && { ...det, source: custom ? "env" : "repo", version: null, model: custom ? "custom" : "repo" };
}

function findRepoDetector(repoRoot, env) {
  const python = env.RHINO_FACADE_PYTHON ||
    join(repoRoot, "data", "venv-det", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
  const run = (name) => join(repoRoot, "data", "det-runs", name, "weights", "best.pt");
  const fused = FUSED_RUNS.map(run);
  const weights = env.RHINO_FACADE_WEIGHTS ||
    (fused.every((p) => existsSync(p)) ? fused.join(delimiter) : null) ||
    DEFAULT_RUNS.map(run).find((p) => existsSync(p)) || run("all11s");
  const script = join(repoRoot, "tools", "facade_yolo.py");
  if (![python, ...weights.split(delimiter).filter(Boolean), script].every((p) => existsSync(p))) return null;
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
  const env = { ...process.env, YOLO_OFFLINE: "1" };
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
          if (det.model) out.model = det.model;
          resolve(JSON.stringify(out));
        } catch { reject(new Error("detector returned no draft")); }
      });
  });
}
