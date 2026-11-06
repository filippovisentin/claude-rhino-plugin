// The installed facade detector: models.json (what the plugin asks for), setup.json (what
// scripts/setup.mjs installed under %LOCALAPPDATA%\claude-rhino), hashes and draft comparison.
// Pure helpers shared by facade-detector.mjs, setup.mjs and doctor.mjs.
import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { createReadStream, existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { delimiter, join } from "node:path";

export const VENV_PYTHON = process.platform === "win32" ? ["Scripts", "python.exe"] : ["bin", "python"];

// %LOCALAPPDATA%\claude-rhino: survives plugin updates, which replace the plugin's own folder.
export function installDir(env = process.env) {
  return join(env.LOCALAPPDATA || join(homedir(), "AppData", "Local"), "claude-rhino");
}

// setup.json, or null when missing, unreadable or not the expected shape.
export function readSetup(dir) {
  const s = readJson(join(dir, "setup.json"));
  if (!s || typeof s !== "object" || Array.isArray(s) || !nonEmpty(s.version)) return null;
  if (!s.verified || typeof s.verified !== "object" || Array.isArray(s.verified)) return null;
  return s;
}

// How the install under installDir(env) relates to the repo's models.json:
// none (no usable setup.json or no manifest), pending (setup unfinished or self-test not ok),
// outdated (other version), incomplete (a default model unverified, hash differs, or a file
// or the venv missing), ok.
export function installState(repoRoot, env = process.env) {
  const dir = installDir(env);
  const manifest = readManifest(repoRoot);
  const setup = readSetup(dir);
  const res = (state) => ({ state, manifest, setup, dir });
  if (!manifest || !setup) return res("none");
  if (setup.version !== manifest.version) return res("outdated");
  const files = modelRuns(manifest).map((run) => join(dir, "models", manifest.version, manifest.files[run].asset));
  const verified = modelRuns(manifest).every((run) => setup.verified[run] === manifest.files[run].sha256);
  if (!verified || !files.every((f) => existsSync(f)) || !existsSync(join(dir, "venv", ...VENV_PYTHON))) {
    return setup.selftest === "ok" ? res("incomplete") : res("pending");
  }
  return res(setup.selftest === "ok" ? "ok" : "pending");
}

// The installed detector when its state is ok (or, with allowPending, when only the self-test is
// missing: setup.mjs runs its self-test on it), else null.
export function installedDetector(repoRoot, env = process.env, { allowPending = false } = {}) {
  const st = installState(repoRoot, env);
  const usable = st.state === "ok" || (allowPending && st.state === "pending" && pendingOnlySelftest(st));
  if (!usable) return null;
  const { manifest, dir } = st;
  return {
    python: join(dir, "venv", ...VENV_PYTHON),
    weights: manifest.default.map((run) => join(dir, "models", manifest.version, manifest.files[run].asset)).join(delimiter),
    configDir: join(dir, "cfg"),
    version: manifest.version,
    model: `${manifest.version} ${manifest.default.join("+")}`,
    scene: manifest.scene?.length ? join(dir, "models", manifest.version, manifest.files[manifest.scene[0]].asset) : null,
  };
}

function pendingOnlySelftest({ manifest, setup, dir }) {
  return modelRuns(manifest).every((run) => setup.verified[run] === manifest.files[run].sha256 &&
    existsSync(join(dir, "models", manifest.version, manifest.files[run].asset))) &&
    existsSync(join(dir, "venv", ...VENV_PYTHON));
}

const SHA256 = /^[0-9a-f]{64}$/;
const nonEmpty = (s) => typeof s === "string" && s.length > 0;

function readJson(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return null; }
}

// Every model the install holds: the facade models of "default", then the scene model(s) of the
// optional "scene" list (tools/silhouette.py).
export function modelRuns(manifest) {
  return [...manifest.default, ...(manifest.scene ?? [])];
}

// models.json of the repo, or null when it is missing or does not describe the default models fully.
export function readManifest(repoRoot) {
  const m = readJson(join(repoRoot, "models.json"));
  if (!m || typeof m !== "object" || !nonEmpty(m.version) || !nonEmpty(m.release)) return null;
  if (!Array.isArray(m.default) || !m.default.length || !m.files || typeof m.files !== "object") return null;
  if (m.scene !== undefined && (!Array.isArray(m.scene) || !m.scene.every(nonEmpty))) return null;
  for (const run of modelRuns(m)) {
    const f = m.files[run];
    if (!f || !nonEmpty(f.asset) || !SHA256.test(f.sha256 ?? "") || !Number.isInteger(f.bytes) || f.bytes <= 0) return null;
  }
  return m;
}

export function sha256File(path) {
  return new Promise((resolve, reject) => {
    const h = createHash("sha256");
    createReadStream(path).on("error", reject).on("data", (c) => h.update(c)).on("end", () => resolve(h.digest("hex")));
  });
}

// Differences between two drafts, as readable lines; [] when they match: the same count per class,
// and each class's boxes, paired in sorted order, within tol pixels on every coordinate.
export function compareDraft(actual, expected, tol = 4) {
  const byClass = (d) => {
    const m = new Map();
    for (const e of d?.els ?? []) {
      if (!m.has(e.k)) m.set(e.k, []);
      m.get(e.k).push(e.box);
    }
    for (const boxes of m.values()) boxes.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
    return m;
  };
  const a = byClass(actual), e = byClass(expected);
  const out = [];
  for (const k of [...new Set([...e.keys(), ...a.keys()])].sort()) {
    const ab = a.get(k) ?? [], eb = e.get(k) ?? [];
    if (ab.length !== eb.length) { out.push(`${k}: ${ab.length} elements, expected ${eb.length}`); continue; }
    ab.forEach((box, i) => {
      if (box.some((v, j) => Math.abs(v - eb[i][j]) > tol)) out.push(`${k} #${i + 1}: box [${box}] expected [${eb[i]}]`);
    });
  }
  return out;
}

function execQuiet(file, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(file, args, { windowsHide: true, timeout: 30_000, ...opts, shell: false }, (err, stdout, stderr) =>
      resolve({ code: err ? (typeof err.code === "number" ? err.code : 1) : 0, stdout: String(stdout ?? ""), stderr: String(stderr ?? "") }));
  });
}

const FIX = "node scripts/setup.mjs";
const GPU_PROBE = "import json,torch;c=torch.cuda.is_available() and torch.cuda.device_count()>0;" +
  "print(json.dumps([torch.__version__,c,torch.cuda.get_device_name(0) if c else None]))";

// The doctor's detector lines: [{status: ok|warn|fail|info, check: "detector", detail}].
export async function detectorReport(repoRoot, env = process.env, exec = execQuiet) {
  const line = (status, detail) => ({ status, check: "detector", detail });
  const { findDetector } = await import("./facade-detector.mjs");
  const det = findDetector(repoRoot, env);
  if (det?.source === "env") return [line("info", `using RHINO_FACADE_PYTHON / RHINO_FACADE_WEIGHTS: ${det.weights}`)];
  const st = installState(repoRoot, env);
  const firstBad = () => {
    const r = modelRuns(st.manifest).find((run) => st.setup.verified[run] !== st.manifest.files[run].sha256) ?? st.manifest.default[0];
    return st.manifest.files[r].asset;
  };
  const out = [];
  if (det?.source === "repo") out.push(line("info", `using repo data/ (development): ${det.weights}`));
  if (st.state === "none") return out.length ? out : [line("info", `not installed (optional): ${FIX}`)];
  if (st.state === "pending") return [...out, line("warn", `setup not finished: ${FIX}`)];
  if (st.state === "outdated") return [...out, line("warn", `models ${st.setup.version} < ${st.manifest.version}: ${FIX}`)];
  if (st.state === "incomplete") return [...out, line("fail", `models ${firstBad()} sha256 mismatch: ${FIX}`)];
  if (det?.source === "repo") return out;

  const inst = installedDetector(repoRoot, env);
  const py = await exec(inst.python, ["-I", "-c", GPU_PROBE], { timeout: 30_000 });
  let probe = null;
  try { probe = JSON.parse(py.stdout.trim().split(/\r?\n/).pop()); } catch { /* reported below */ }
  if (py.code !== 0 || !Array.isArray(probe)) return [line("fail", `python ${inst.python} does not start: ${FIX}`)];
  const [torchVersion, cuda, gpuName] = probe;
  out.push(line("ok", `python ${inst.python} (torch ${torchVersion} ${st.setup.device ?? (cuda ? "cuda" : "cpu")})`));
  for (const run of modelRuns(st.manifest)) {
    const { asset, sha256 } = st.manifest.files[run];
    if (await sha256File(join(st.dir, "models", st.manifest.version, asset)) !== sha256) {
      return [...out, line("fail", `models ${asset} sha256 mismatch: ${FIX}`)];
    }
  }
  out.push(line("ok", `models ${modelRuns(st.manifest).join("+")} ${st.manifest.version}, sha256 verified`));
  if (cuda) {
    const smi = await exec("nvidia-smi", ["--query-gpu=driver_version", "--format=csv,noheader"], { timeout: 30_000 });
    const driver = smi.code === 0 ? smi.stdout.trim().split(/\r?\n/)[0].split(",").pop().trim() : "?";
    out.push(line("ok", `gpu ${gpuName}, driver ${driver}`));
  } else {
    out.push(line("warn", "gpu not available, running on CPU"));
  }
  return out;
}
