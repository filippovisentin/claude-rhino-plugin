// The installed facade detector: models.json (what the plugin asks for), setup.json (what
// scripts/setup.mjs installed under %LOCALAPPDATA%\claude-rhino), hashes and draft comparison.
// Pure helpers shared by facade-detector.mjs, setup.mjs and doctor.mjs.
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
  const files = manifest.default.map((run) => join(dir, "models", manifest.version, manifest.files[run].asset));
  const verified = manifest.default.every((run) => setup.verified[run] === manifest.files[run].sha256);
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
  };
}

function pendingOnlySelftest({ manifest, setup, dir }) {
  return manifest.default.every((run) => setup.verified[run] === manifest.files[run].sha256 &&
    existsSync(join(dir, "models", manifest.version, manifest.files[run].asset))) &&
    existsSync(join(dir, "venv", ...VENV_PYTHON));
}

const SHA256 = /^[0-9a-f]{64}$/;
const nonEmpty = (s) => typeof s === "string" && s.length > 0;

function readJson(path) {
  try { return JSON.parse(readFileSync(path, "utf8")); } catch { return null; }
}

// models.json of the repo, or null when it is missing or does not describe the default models fully.
export function readManifest(repoRoot) {
  const m = readJson(join(repoRoot, "models.json"));
  if (!m || typeof m !== "object" || !nonEmpty(m.version) || !nonEmpty(m.release)) return null;
  if (!Array.isArray(m.default) || !m.default.length || !m.files || typeof m.files !== "object") return null;
  for (const run of m.default) {
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
