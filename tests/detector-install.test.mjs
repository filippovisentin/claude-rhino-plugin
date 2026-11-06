import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { compareDraft, readManifest, sha256File } from "../scripts/detector-install.mjs";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const tmp = (name = "di-") => mkdtempSync(join(tmpdir(), name));
const HEX = "a".repeat(64);
const manifest = (over = {}) => ({
  version: "2026.11.06", release: "models-2026.11.06", default: ["parts2m", "parts11s"],
  files: { parts2m: { asset: "parts2m.pt", sha256: HEX, bytes: 1 }, parts11s: { asset: "parts11s.pt", sha256: HEX, bytes: 1 } },
  ...over,
});
const writeManifest = (m) => {
  const d = tmp();
  writeFileSync(join(d, "models.json"), typeof m === "string" ? m : JSON.stringify(m));
  return d;
};

test("readManifest reads the repo's models.json", () => {
  const m = readManifest(repoRoot);
  assert.equal(m.version, "2026.11.06");
  assert.equal(m.release, "models-2026.11.06");
  assert.deepEqual(m.default, ["parts2m", "parts11s"]);
});

test("readManifest refuses missing, truncated or inconsistent manifests", () => {
  assert.equal(readManifest(tmp()), null);
  assert.equal(readManifest(writeManifest('{"version"')), null);
  const short = manifest();
  short.files.parts2m.sha256 = "a".repeat(63);
  assert.equal(readManifest(writeManifest(short)), null);
  const upper = manifest();
  upper.files.parts2m.sha256 = "A".repeat(64);
  assert.equal(readManifest(writeManifest(upper)), null);
  assert.equal(readManifest(writeManifest(manifest({ default: ["parts2m", "nope"] }))), null);
  assert.equal(readManifest(writeManifest(manifest({ default: [] }))), null);
  assert.equal(readManifest(writeManifest(manifest({ version: "" }))), null);
  const bytes = manifest();
  bytes.files.parts11s.bytes = 0;
  assert.equal(readManifest(writeManifest(bytes)), null);
  assert.ok(readManifest(writeManifest(manifest())));
});

test("sha256File hashes a file as lowercase hex", async () => {
  const f = join(tmp(), "abc.txt");
  writeFileSync(f, "abc");
  assert.equal(await sha256File(f), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
});

test("compareDraft: equal drafts, a box moved 5 px, an element missing", () => {
  const e = { els: [{ k: "window", box: [10, 10, 50, 80] }, { k: "window", box: [100, 10, 140, 80] }, { k: "door", box: [60, 90, 90, 160] }] };
  assert.deepEqual(compareDraft(e, e), []);
  const shuffled = { els: [e.els[2], e.els[1], e.els[0]] };
  assert.deepEqual(compareDraft(shuffled, e), []);
  const within = { els: [{ k: "window", box: [14, 10, 50, 80] }, e.els[1], e.els[2]] };
  assert.deepEqual(compareDraft(within, e), []);
  const moved = { els: [{ k: "window", box: [15, 10, 50, 80] }, e.els[1], e.els[2]] };
  const d = compareDraft(moved, e);
  assert.equal(d.length, 1);
  assert.match(d[0], /window/);
  const missing = { els: [e.els[0], e.els[1]] };
  const d2 = compareDraft(missing, e);
  assert.equal(d2.length, 1);
  assert.match(d2[0], /door/);
  assert.match(d2[0], /0/);
  assert.match(d2[0], /1/);
});

// --- Task 3: the installed detector ------------------------------------------------------------
import { mkdirSync } from "node:fs";
import { delimiter } from "node:path";
import { installDir, installState, installedDetector, readSetup } from "../scripts/detector-install.mjs";
import { findDetector, runDetector } from "../scripts/facade-detector.mjs";

const VENV_PY = process.platform === "win32" ? ["Scripts", "python.exe"] : ["bin", "python"];
import { createHash } from "node:crypto";
const SHA = Object.fromEntries(["parts2m", "parts11s"].map((r) => [r, createHash("sha256").update(r).digest("hex")]));

// A repo with models.json and the detector script, and a LOCALAPPDATA whose name has a space
// and an accent, holding a complete install; over() edits setup.json before it is written.
function fakeInstall(over = (s) => s, { repoData = false } = {}) {
  const root = tmp("di-inst-");
  const repo = join(root, "repo");
  mkdirSync(join(repo, "tools"), { recursive: true });
  writeFileSync(join(repo, "tools", "facade_yolo.py"), "");
  const m = manifest();
  m.files.parts2m.sha256 = SHA.parts2m;
  m.files.parts11s.sha256 = SHA.parts11s;
  writeFileSync(join(repo, "models.json"), JSON.stringify(m));
  if (repoData) {
    const py = join(repo, "data", "venv-det", ...VENV_PY);
    mkdirSync(join(py, ".."), { recursive: true });
    writeFileSync(py, "");
    for (const r of ["parts2m", "parts11s"]) {
      mkdirSync(join(repo, "data", "det-runs", r, "weights"), { recursive: true });
      writeFileSync(join(repo, "data", "det-runs", r, "weights", "best.pt"), "");
    }
  }
  const env = { LOCALAPPDATA: join(root, "Filippo Visentì") };
  const dir = installDir(env);
  const py = join(dir, "venv", ...VENV_PY);
  mkdirSync(join(py, ".."), { recursive: true });
  writeFileSync(py, "");
  mkdirSync(join(dir, "models", "2026.11.06"), { recursive: true });
  for (const r of ["parts2m", "parts11s"]) writeFileSync(join(dir, "models", "2026.11.06", r + ".pt"), r);
  const setup = over({ version: "2026.11.06", device: "cuda", python: py, verified: { ...SHA }, selftest: "ok", date: "2026-11-06T12:00:00Z" });
  if (setup !== undefined) writeFileSync(join(dir, "setup.json"), typeof setup === "string" ? setup : JSON.stringify(setup));
  return { repo, env, dir };
}

test("installDir lives under LOCALAPPDATA and keeps spaces and accents", () => {
  assert.equal(installDir({ LOCALAPPDATA: "C:\\Users\\Filippo Visentì\\AppData\\Local" }),
    join("C:\\Users\\Filippo Visentì\\AppData\\Local", "claude-rhino"));
});

test("no setup.json: state none, no installed detector", () => {
  const { repo, env } = fakeInstall(() => undefined);
  assert.equal(installState(repo, env).state, "none");
  assert.equal(installedDetector(repo, env), null);
});

test("a complete install is found first, with its path intact", () => {
  const { repo, env, dir } = fakeInstall();
  assert.equal(installState(repo, env).state, "ok");
  const d = findDetector(repo, env);
  assert.equal(d.source, "installed");
  assert.equal(d.version, "2026.11.06");
  assert.equal(d.weights, join(dir, "models", "2026.11.06", "parts2m.pt") + delimiter + join(dir, "models", "2026.11.06", "parts11s.pt"));
  assert.ok(d.python.includes("Filippo Visentì"));
  assert.equal(d.configDir, join(dir, "cfg"));
  assert.equal(d.model, "2026.11.06 parts2m+parts11s");
});

test("a truncated setup.json counts as no install, without throwing", () => {
  const { repo, env, dir } = fakeInstall(() => '{"version"');
  assert.equal(readSetup(dir), null);
  assert.equal(installState(repo, env).state, "none");
  assert.equal(findDetector(repo, env), null);
});

test("a setup still running (selftest pending) is not used", () => {
  const { repo, env } = fakeInstall((s) => ({ ...s, selftest: "pending" }));
  assert.equal(installState(repo, env).state, "pending");
  assert.equal(installedDetector(repo, env), null);
  assert.ok(installedDetector(repo, env, { allowPending: true }));
});

test("an older install is not used; the repo's data/ takes over", () => {
  const { repo, env } = fakeInstall((s) => ({ ...s, version: "2026.10.01" }), { repoData: true });
  assert.equal(installState(repo, env).state, "outdated");
  const d = findDetector(repo, env);
  assert.equal(d.source, "repo");
  assert.equal(d.model, "repo");
});

test("a hash in setup.json that differs from models.json: incomplete", () => {
  const { repo, env } = fakeInstall((s) => ({ ...s, verified: { ...s.verified, parts11s: "3".repeat(64) } }));
  assert.equal(installState(repo, env).state, "incomplete");
  assert.equal(installedDetector(repo, env), null);
});

test("RHINO_FACADE_PYTHON / RHINO_FACADE_WEIGHTS still win over an install", () => {
  const { repo, env, dir } = fakeInstall();
  const w = join(dir, "models", "2026.11.06", "parts2m.pt");
  const d = findDetector(repo, { ...env, RHINO_FACADE_PYTHON: join(dir, "venv", ...VENV_PY), RHINO_FACADE_WEIGHTS: w });
  assert.equal(d.source, "env");
  assert.equal(d.weights, w);
  assert.equal(d.model, "custom");
});

test("runDetector runs offline and labels the draft with the model", async () => {
  const { repo, env } = fakeInstall();
  const d = findDetector(repo, env);
  let seen;
  const text = await runDetector(d, "C:\\a.jpg", 0.25, (f, a, o, cb) => { seen = o; cb(null, '{"img":[1,2],"els":[]}'); });
  assert.equal(seen.env.YOLO_OFFLINE, "1");
  assert.equal(seen.env.YOLO_CONFIG_DIR, d.configDir);
  assert.equal(JSON.parse(text).model, "2026.11.06 parts2m+parts11s");
});

// --- Task 5: the doctor's detector lines -------------------------------------------------------
import { detectorReport } from "../scripts/detector-install.mjs";

// exec for the doctor: the detector's Python prints [torch version, cuda, gpu name]; nvidia-smi the driver.
const doctorExec = ({ cuda = true, pyCode = 0 } = {}) => async (file, args) => {
  if (/nvidia-smi/.test(file)) return { code: 0, stdout: "NVIDIA GeForce RTX 5070 Ti Laptop GPU, 596.36\n", stderr: "" };
  if (pyCode) return { code: pyCode, stdout: "", stderr: "boom" };
  return { code: 0, stdout: JSON.stringify(["2.11.0+cu128", cuda, cuda ? "NVIDIA GeForce RTX 5070 Ti Laptop GPU" : null]) + "\n", stderr: "" };
};
const lines = async (repo, env, exec = doctorExec()) => (await detectorReport(repo, env, exec)).map((r) => `${r.status} ${r.detail}`);

test("doctor: a verified install on a GPU gives three OK lines", async () => {
  const { repo, env, dir } = fakeInstall();
  const l = await lines(repo, env);
  assert.equal(l.length, 3);
  assert.equal(l[0], `ok python ${join(dir, "venv", ...VENV_PY)} (torch 2.11.0+cu128 cuda)`);
  assert.equal(l[1], "ok models parts2m+parts11s 2026.11.06, sha256 verified");
  assert.equal(l[2], "ok gpu NVIDIA GeForce RTX 5070 Ti Laptop GPU, driver 596.36");
});

test("doctor: no GPU seen by torch is a warning", async () => {
  const { repo, env } = fakeInstall();
  const l = await lines(repo, env, doctorExec({ cuda: false }));
  assert.equal(l[2], "warn gpu not available, running on CPU");
});

test("doctor: a Python that does not start fails", async () => {
  const { repo, env, dir } = fakeInstall();
  const l = await lines(repo, env, doctorExec({ pyCode: 1 }));
  assert.ok(l.includes(`fail python ${join(dir, "venv", ...VENV_PY)} does not start: node scripts/setup.mjs`));
});

test("doctor: a model file changed on disk fails with its name", async () => {
  const { repo, env, dir } = fakeInstall();
  writeFileSync(join(dir, "models", "2026.11.06", "parts11s.pt"), "changed");
  const l = await lines(repo, env);
  assert.ok(l.includes("fail models parts11s.pt sha256 mismatch: node scripts/setup.mjs"));
});

test("doctor: not installed, unfinished, outdated, inconsistent", async () => {
  const none = fakeInstall(() => undefined);
  assert.deepEqual(await lines(none.repo, none.env), ["info not installed (optional): node scripts/setup.mjs"]);
  const broken = fakeInstall(() => '{"version"');
  assert.deepEqual(await lines(broken.repo, broken.env), ["info not installed (optional): node scripts/setup.mjs"]);
  const pend = fakeInstall((s) => ({ ...s, selftest: "pending" }));
  assert.deepEqual(await lines(pend.repo, pend.env), ["warn setup not finished: node scripts/setup.mjs"]);
  const old = fakeInstall((s) => ({ ...s, version: "2026.10.01" }));
  assert.deepEqual(await lines(old.repo, old.env), ["warn models 2026.10.01 < 2026.11.06: node scripts/setup.mjs"]);
  const inc = fakeInstall((s) => ({ ...s, verified: { ...s.verified, parts11s: "3".repeat(64) } }));
  assert.deepEqual(await lines(inc.repo, inc.env), ["fail models parts11s.pt sha256 mismatch: node scripts/setup.mjs"]);
});

test("doctor: the repo's data/ and the env variables are reported as such", async () => {
  const dev = fakeInstall(() => undefined, { repoData: true });
  const l = await lines(dev.repo, dev.env);
  assert.equal(l.length, 1);
  assert.match(l[0], /^info using repo data\/ \(development\): .*best\.pt/);
  const { repo, env, dir } = fakeInstall();
  const w = join(dir, "models", "2026.11.06", "parts2m.pt");
  const l2 = await lines(repo, { ...env, RHINO_FACADE_PYTHON: join(dir, "venv", ...VENV_PY), RHINO_FACADE_WEIGHTS: w });
  assert.deepEqual(l2, [`info using RHINO_FACADE_PYTHON / RHINO_FACADE_WEIGHTS: ${w}`]);
});

// --- Final review fixes ------------------------------------------------------------------------
test("an install that a rerun of the setup is replacing is not run, even after the plugin started", async () => {
  const { repo, env, dir } = fakeInstall();
  const d = findDetector(repo, env);
  assert.equal(d.source, "installed");
  const s = JSON.parse(readFileSync(join(dir, "setup.json"), "utf8"));
  writeFileSync(join(dir, "setup.json"), JSON.stringify({ ...s, selftest: "pending" }));
  let ran = false;
  await assert.rejects(runDetector(d, "C:\a.jpg", 0.25, (f, a, o, cb) => { ran = true; cb(null, '{"img":[1,2],"els":[]}'); }),
    /setup/);
  assert.equal(ran, false);
});

test("the doctor's Python probe runs isolated (-I)", async () => {
  const { repo, env } = fakeInstall();
  const seen = [];
  await detectorReport(repo, env, async (file, args) => { seen.push(args); return doctorExec()(file, args); });
  assert.equal(seen.find((a) => a.includes("-c"))[0], "-I");
});
