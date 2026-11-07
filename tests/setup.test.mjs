import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join } from "node:path";
import { setup } from "../scripts/setup.mjs";
import { installDir, VENV_PYTHON } from "../scripts/detector-install.mjs";

const RUNS = ["parts2m", "parts11s"];
const content = (run) => `weights of ${run}`;
const sha = (s) => createHash("sha256").update(s).digest("hex");
const EXPECTED = { img: [960, 1280], els: [{ k: "window", box: [10, 10, 50, 80] }] };

// A repo with what setup.mjs reads, and a LOCALAPPDATA whose name has a space and an accent.
function world() {
  const root = mkdtempSync(join(tmpdir(), "setup-"));
  const repo = join(root, "repo");
  mkdirSync(join(repo, "tools"), { recursive: true });
  writeFileSync(join(repo, "tools", "facade_detect.py"), "");
  mkdirSync(join(repo, "tests", "fixtures", "detector"), { recursive: true });
  writeFileSync(join(repo, "tests", "fixtures", "detector", "c_0075.jpg"), "jpeg");
  writeFileSync(join(repo, "tests", "fixtures", "detector", "expected.json"), JSON.stringify(EXPECTED));
  writeFileSync(join(repo, "requirements-detector.txt"), "torch\n");
  writeFileSync(join(repo, "requirements-detector-cpu.txt"), "torch\n");
  writeFileSync(join(repo, "models.json"), JSON.stringify({
    version: "2026.11.06", release: "models-2026.11.06", default: RUNS, scene: ["scene2"],
    files: Object.fromEntries([...RUNS, "scene2"].map((r) => [r, { asset: `${r}.pt`, sha256: sha(content(r)), bytes: content(r).length }])),
  }));
  return { repo, env: { LOCALAPPDATA: join(root, "Filippo Visentì") } };
}

// Fake commands. over: {cmd: result or (args) => result} replaces one behaviour.
function fakeExec(over = {}) {
  const calls = [];
  const exec = async (file, args, opts) => {
    calls.push({ file, args, opts });
    const name = basename(file).replace(/\.exe$/, "");
    const key = name === "uv" || name === "gh" ? `${name} ${args[0]}${args[1] && !args[1].startsWith("-") ? " " + args[1] : ""}` : name;
    if (key in over) return typeof over[key] === "function" ? over[key](args) : over[key];
    if (name === "nvidia-smi") return { code: 0, stdout: "NVIDIA GeForce RTX 5070 Ti Laptop GPU, 596.36\n", stderr: "" };
    if (key === "uv venv") {
      const py = join(args[args.length - 1], ...VENV_PYTHON);
      mkdirSync(join(py, ".."), { recursive: true });
      writeFileSync(py, "");
    }
    if (key === "gh release download") {
      const asset = args[args.indexOf("-p") + 1], dir = args[args.indexOf("-D") + 1];
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, asset), content(asset.replace(/\.pt$/, "")));
    }
    if (name === "python") return { code: existsSync(file) ? 0 : 1, stdout: "", stderr: "" };
    return { code: 0, stdout: "", stderr: "" };
  };
  return { exec, calls };
}

const detect = async () => JSON.stringify(EXPECTED);
const run = (w, x, extra = {}) => setup({ repoRoot: w.repo, env: w.env, exec: x.exec, detect, freeBytes: () => 1e12, log: () => {}, ...extra });
const readSetupJson = (w) => JSON.parse(readFileSync(join(installDir(w.env), "setup.json"), "utf8"));

test("a full setup installs, verifies both models and passes the self-test", async () => {
  const w = world(), x = fakeExec();
  const r = await run(w, x);
  assert.equal(r.ok, true, r.message);
  const s = readSetupJson(w);
  assert.deepEqual(s.verified, { parts2m: sha(content("parts2m")), parts11s: sha(content("parts11s")), scene2: sha(content("scene2")) });
  assert.equal(s.selftest, "ok");
  assert.equal(s.device, "cuda");
  assert.equal(s.version, "2026.11.06");
  for (const r of [...RUNS, "scene2"]) assert.ok(existsSync(join(installDir(w.env), "models", "2026.11.06", `${r}.pt`)));
  const install = x.calls.find((c) => c.args[0] === "pip");
  assert.ok(install.args.includes(join(w.repo, "requirements-detector.txt")));
});

test("a second run touches neither uv nor the release", async () => {
  const w = world();
  await run(w, fakeExec());
  const x = fakeExec();
  const r = await run(w, x);
  assert.equal(r.ok, true, r.message);
  assert.ok(!x.calls.some((c) => basename(c.file).startsWith("uv")));
  assert.ok(!x.calls.some((c) => c.args[0] === "release" && c.args[1] === "download"));
});

test("an old driver stops the setup unless --cpu, which uses the CPU requirements", async () => {
  const old = { "nvidia-smi": { code: 0, stdout: "NVIDIA GeForce GTX, 566.03\n", stderr: "" } };
  const w = world();
  const r = await run(w, fakeExec(old));
  assert.equal(r.ok, false);
  assert.equal(r.step, "prereqs");
  assert.match(r.message, /570/);
  const x = fakeExec(old);
  const r2 = await run(w, x, { cpu: true });
  assert.equal(r2.ok, true, r2.message);
  assert.ok(x.calls.find((c) => c.args[0] === "pip").args.includes(join(w.repo, "requirements-detector-cpu.txt")));
  assert.equal(readSetupJson(w).device, "cpu");
});

test("a download with the wrong content is deleted and never installed", async () => {
  const w = world();
  const bad = fakeExec({
    "gh release download": (args) => {
      const dir = args[args.indexOf("-D") + 1];
      mkdirSync(dir, { recursive: true });
      writeFileSync(join(dir, args[args.indexOf("-p") + 1]), "tampered");
      return { code: 0, stdout: "", stderr: "" };
    },
  });
  const r = await run(w, bad);
  assert.equal(r.ok, false);
  assert.equal(r.step, "models");
  assert.ok(!existsSync(join(installDir(w.env), "models", "2026.11.06", "parts2m.pt")));
  assert.deepEqual(readdirSync(join(installDir(w.env), "models", ".tmp")), []);
  const s = readSetupJson(w);
  assert.equal(s.verified.parts2m, undefined);
  assert.equal(s.selftest, "pending");
});

test("an asset missing from the release stops the setup with its name", async () => {
  const w = world();
  const r = await run(w, fakeExec({ "gh release download": { code: 1, stdout: "", stderr: "no assets match the file pattern" } }));
  assert.equal(r.ok, false);
  assert.equal(r.step, "models");
  assert.match(r.message, /parts2m\.pt/);
});

test("a partial file left in models/.tmp is removed before the download", async () => {
  const w = world();
  const tmpDir = join(installDir(w.env), "models", ".tmp");
  mkdirSync(tmpDir, { recursive: true });
  writeFileSync(join(tmpDir, "parts2m.pt"), "half a file");
  const r = await run(w, fakeExec());
  assert.equal(r.ok, true, r.message);
  assert.equal(readFileSync(join(installDir(w.env), "models", "2026.11.06", "parts2m.pt"), "utf8"), content("parts2m"));
});

test("a self-test that differs from expected.json fails and is recorded", async () => {
  const w = world();
  const r = await run(w, fakeExec(), { detect: async () => JSON.stringify({ img: [960, 1280], els: [] }) });
  assert.equal(r.ok, false);
  assert.equal(r.step, "selftest");
  const s = readSetupJson(w);
  assert.equal(s.selftest, "fail");
  assert.ok(s.diff.some((l) => /window/.test(l)));
});

test("paths reach every command whole, never through a shell", async () => {
  const w = world(), x = fakeExec();
  await run(w, x);
  for (const c of x.calls) assert.notEqual(c.opts?.shell, true);
  const venv = x.calls.find((c) => c.args[0] === "venv");
  assert.equal(venv.args[venv.args.length - 1], join(installDir(w.env), "venv"));
  assert.ok(venv.args[venv.args.length - 1].includes("Filippo Visentì"));
  const dl = x.calls.find((c) => c.args[1] === "download");
  assert.ok(dl.args[dl.args.indexOf("-D") + 1].includes("Filippo Visentì"));
});

test("a venv still in use (Windows refuses to delete it) stops the setup with a clear message", async () => {
  const w = world();
  await run(w, fakeExec());
  const busy = () => { const e = new Error("EBUSY: resource busy or locked"); e.code = "EBUSY"; throw e; };
  const r = await run(w, fakeExec(), { cpu: true, rm: busy });
  assert.equal(r.ok, false);
  assert.equal(r.step, "python");
  assert.match(r.message, /in use/);
});

test("Python probes run isolated (-I), so files in the current folder are never imported", async () => {
  const w = world();
  await run(w, fakeExec());
  const x = fakeExec();
  await run(w, x);
  const probe = x.calls.find((c) => c.args.includes("-c"));
  assert.equal(probe.args[0], "-I");
});

test("gh missing is reported as missing, not as signed out", async () => {
  const w = world();
  const r = await run(w, fakeExec({ "gh auth status": { code: 127, stdout: "", stderr: "" } }));
  assert.equal(r.ok, false);
  assert.match(r.message, /gh not found/);
});

test("an install of an older version is outdated and the setup brings it up to date", async () => {
  const w = world();
  await run(w, fakeExec());
  const m = JSON.parse(readFileSync(join(w.repo, "models.json"), "utf8"));
  writeFileSync(join(w.repo, "models.json"), JSON.stringify({ ...m, version: "2026.11.07", release: "models-2026.11.07" }));
  const { installState } = await import("../scripts/detector-install.mjs");
  assert.equal(installState(w.repo, w.env).state, "outdated");
  const x = fakeExec();
  const r = await run(w, x);
  assert.equal(r.ok, true, r.message);
  assert.equal(x.calls.filter((c) => c.args[1] === "download").length, 3);
  assert.equal(readSetupJson(w).version, "2026.11.07");
});

test("--tools makes only the light Python: no GPU check, no gh, no models", async () => {
  const w = world();
  writeFileSync(join(w.repo, "requirements-tools.txt"), "numpy\n");
  const x = fakeExec();
  const r = await run(w, x, { tools: true });
  assert.equal(r.ok, true, r.message);
  const files = x.calls.map((c) => basename(c.file).replace(/\.exe$/, ""));
  assert.ok(!files.includes("nvidia-smi") && !files.includes("gh"), files.join(","));
  const venv = x.calls.find((c) => c.args[0] === "venv");
  assert.equal(venv.args[venv.args.length - 1], join(installDir(w.env), "venv-tools"));
  const pip = x.calls.find((c) => c.args[0] === "pip");
  assert.ok(pip.args.includes(join(w.repo, "requirements-tools.txt")));
  assert.equal(existsSync(join(installDir(w.env), "setup.json")), false);
  // a second run finds it done and installs nothing
  const y = fakeExec({ python: { code: 0, stdout: "", stderr: "" } });
  assert.equal((await run(w, y, { tools: true })).ok, true);
  assert.equal(y.calls.some((c) => c.args[0] === "venv" || c.args[0] === "pip"), false);
});
