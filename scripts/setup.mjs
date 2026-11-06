// Installs the facade detector for this plugin under %LOCALAPPDATA%\claude-rhino:
//   node scripts/setup.mjs [--cpu]
// A Python made by uv with pinned versions, the default models of models.json downloaded from this
// private repository's release and checked against their sha256, then a self-test on the fixture
// photo. Every step is skipped when already done, so running it again is always safe. It deletes
// only inside %LOCALAPPDATA%\claude-rhino, closes no process and changes no system setting.
import { execFile } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, renameSync, rmSync, statfsSync, writeFileSync } from "node:fs";
import { dirname, join, relative, isAbsolute } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { compareDraft, installDir, installedDetector, readManifest, readSetup, sha256File, VENV_PYTHON } from "./detector-install.mjs";
import { runDetector } from "./facade-detector.mjs";

export const REPO = "filippovisentin/claude-rhino-plugin";
const MIN_DRIVER = 570; // CUDA 12.8
const GB = 2 ** 30;
const UV_HELP = "uv not found: install it (https://docs.astral.sh/uv/getting-started/installation/), then run the setup again";

// execFile that never rejects: {code, stdout, stderr}; code 127 when the program is missing.
export function defaultExec(file, args, opts = {}) {
  return new Promise((resolve) => {
    execFile(file, args, { windowsHide: true, maxBuffer: 64 * 2 ** 20, ...opts, shell: false }, (err, stdout, stderr) => {
      const code = !err ? 0 : typeof err.code === "number" ? err.code : err.code === "ENOENT" ? 127 : 1;
      resolve({ code, stdout: String(stdout ?? ""), stderr: String(stderr ?? "") });
    });
  });
}

function defaultFreeBytes(path) {
  if (typeof statfsSync !== "function") return null;
  let p = path;
  while (!existsSync(p) && dirname(p) !== p) p = dirname(p);
  const s = statfsSync(p);
  return s.bavail * s.bsize;
}

const inside = (dir, p) => { const r = relative(dir, p); return r && !r.startsWith("..") && !isAbsolute(r); };

export async function setup({ repoRoot, env = process.env, cpu = false, exec = defaultExec, detect = runDetector,
  freeBytes = defaultFreeBytes, rm = rmSync, log = console.log } = {}) {
  const fail = (step, message) => ({ ok: false, step, message });
  const run = (file, args, timeout = 120_000) => exec(file, args, { shell: false, windowsHide: true, timeout });
  const manifest = readManifest(repoRoot);
  if (!manifest) return fail("prereqs", `models.json missing or invalid in ${repoRoot}`);
  const dir = installDir(env);
  const device = cpu ? "cpu" : "cuda";
  const venv = join(dir, "venv"), python = join(venv, ...VENV_PYTHON);
  const modelDir = join(dir, "models", manifest.version), tmpDir = join(dir, "models", ".tmp");
  let state = readSetup(dir) ?? { verified: {} };
  if (state.version !== manifest.version) state = { ...state, version: manifest.version, verified: {} };
  const save = (patch) => {
    state = { ...state, ...patch, date: new Date().toISOString() };
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "setup.json.tmp"), JSON.stringify(state, null, 1));
    renameSync(join(dir, "setup.json.tmp"), join(dir, "setup.json"));
  };

  // What is missing decides which checks are needed.
  const venvOk = existsSync(python) && state.device === device && (await run(python, ["-I", "-c", "import torch, ultralytics"], 60_000)).code === 0;
  const missing = manifest.default.filter((r) => state.verified[r] !== manifest.files[r].sha256 ||
    !existsSync(join(modelDir, manifest.files[r].asset)));

  // 1. prereqs
  if (!cpu) {
    const smi = await run("nvidia-smi", ["--query-gpu=name,driver_version", "--format=csv,noheader"], 30_000);
    if (smi.code !== 0) return fail("prereqs", "NVIDIA driver not found (nvidia-smi): install the NVIDIA driver, or run the setup with --cpu");
    const [name, driver = ""] = smi.stdout.trim().split(/\r?\n/)[0].split(",").map((s) => s.trim());
    if (!(parseInt(driver, 10) >= MIN_DRIVER)) {
      return fail("prereqs", `NVIDIA driver ${driver || "?"} on ${name} is older than ${MIN_DRIVER} (needed by CUDA 12.8): update the driver, or run the setup with --cpu`);
    }
  }
  if (!venvOk && (await run("uv", ["--version"], 30_000)).code !== 0) return fail("prereqs", UV_HELP);
  if (missing.length) {
    const auth = await run("gh", ["auth", "status"], 30_000);
    if (auth.code === 127) return fail("prereqs", "gh not found: install GitHub CLI (https://cli.github.com), then run gh auth login");
    if (auth.code !== 0) return fail("prereqs", "gh is not signed in: run gh auth login");
    if ((await run("gh", ["release", "view", manifest.release, "--repo", REPO], 30_000)).code !== 0) {
      return fail("prereqs", `no access to release ${manifest.release} of ${REPO}: ask to be added to the repository, then run gh auth login`);
    }
  }
  if (!venvOk || missing.length) {
    const need = (venvOk ? 0 : cpu ? 2 : 8) * GB + missing.reduce((s, r) => s + manifest.files[r].bytes, 0);
    const free = freeBytes(dir);
    if (free === null) log("disk space not checked (needs Node 18.15 or newer)");
    else if (free < need) return fail("prereqs", `${(free / GB).toFixed(1)} GB free under ${dir}, ${(need / GB).toFixed(1)} GB needed`);
  }

  // 2. python
  if (!venvOk) {
    save({ selftest: "pending" });
    log(`Python: creating ${venv} (${device}), this downloads PyTorch the first time`);
    if (existsSync(venv)) {
      if (!inside(dir, venv)) return fail("python", `refusing to delete ${venv}`);
      try {
        rm(venv, { recursive: true, force: true });
      } catch (e) {
        return fail("python", `${venv} is in use (${e.code ?? e.message}): close the Claude or Rhino sessions that use detect_facade, then run the setup again`);
      }
    }
    const mk = await run("uv", ["venv", "--python", "3.12", venv], 600_000);
    if (mk.code !== 0) return fail("python", `uv venv failed: ${mk.stderr.trim().slice(-400)}`);
    const req = join(repoRoot, cpu ? "requirements-detector-cpu.txt" : "requirements-detector.txt");
    const pip = await run("uv", ["pip", "install", "--python", python, "--index-strategy", "unsafe-best-match", "-r", req], 0);
    if (pip.code !== 0) return fail("python", `uv pip install failed: ${pip.stderr.trim().slice(-400)}`);
    save({ device, python });
  }

  // 3. models
  if (missing.length) {
    save({ selftest: "pending" });
    mkdirSync(modelDir, { recursive: true });
    for (const r of missing) {
      const { asset, sha256 } = manifest.files[r];
      rmSync(tmpDir, { recursive: true, force: true });
      mkdirSync(tmpDir, { recursive: true });
      log(`Model ${r}: downloading ${asset} from ${manifest.release}`);
      const dl = await run("gh", ["release", "download", manifest.release, "--repo", REPO, "-p", asset, "-D", tmpDir, "--clobber"], 600_000);
      const got = join(tmpDir, asset);
      if (dl.code !== 0 || !existsSync(got)) {
        return fail("models", `could not download ${asset} from release ${manifest.release}: ${dl.stderr.trim().slice(-300)}`);
      }
      const h = await sha256File(got);
      if (h !== sha256) {
        rmSync(got, { force: true });
        return fail("models", `${asset}: sha256 ${h} does not match models.json (${sha256}); the file was deleted`);
      }
      renameSync(got, join(modelDir, asset));
      save({ verified: { ...state.verified, [r]: sha256 } });
    }
  }

  // 4. self-test
  if (state.selftest !== "ok" || !venvOk || missing.length) {
    const inst = installedDetector(repoRoot, env, { allowPending: true });
    if (!inst) return fail("selftest", "the install is incomplete; run the setup again");
    const fixture = join(repoRoot, "tests", "fixtures", "detector");
    let diff;
    try {
      const out = JSON.parse(await detect({ ...inst, script: join(repoRoot, "tools", "facade_detect.py") }, join(fixture, "c_0075.jpg"), 0.25));
      diff = compareDraft(out, JSON.parse(readFileSync(join(fixture, "expected.json"), "utf8")));
    } catch (e) {
      diff = [`detector did not run: ${e.message}`];
    }
    save({ selftest: diff.length ? "fail" : "ok", diff });
    if (diff.length) return fail("selftest", `the self-test differs from the reference:\n  ${diff.join("\n  ")}`);
  }

  return { ok: true, step: "done", message: `detector ready: models ${manifest.version} (${manifest.default.join("+")}), ${state.device}. Check with: node scripts/doctor.mjs` };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
  const r = await setup({ repoRoot, cpu: process.argv.includes("--cpu") });
  console.log(r.ok ? r.message : `setup stopped at ${r.step}: ${r.message}`);
  process.exitCode = r.ok ? 0 : 1;
}
