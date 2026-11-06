// The installed facade detector: models.json (what the plugin asks for), setup.json (what
// scripts/setup.mjs installed under %LOCALAPPDATA%\claude-rhino), hashes and draft comparison.
// Pure helpers shared by facade-detector.mjs, setup.mjs and doctor.mjs.
import { createHash } from "node:crypto";
import { createReadStream, readFileSync } from "node:fs";
import { join } from "node:path";

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
