import { test } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFile } from "node:child_process";
import { mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { TOOLS, toolCommand } from "../scripts/run-tool.mjs";
import { installDir, VENV_PYTHON } from "../scripts/detector-install.mjs";

const repoRoot = fileURLToPath(new URL("..", import.meta.url));
const sha = (s) => createHash("sha256").update(s).digest("hex");

// A repo copy with the runtime tools' names and an install (with the scene model) under a
// LOCALAPPDATA whose name has a space and an accent.
function world({ install = true } = {}) {
  const root = mkdtempSync(join(tmpdir(), "run-tool-"));
  const repo = join(root, "repo");
  mkdirSync(join(repo, "tools"), { recursive: true });
  for (const f of ["facade_detect.py", "rectify.py", "photo3d.py", "silhouette.py", "photo_tools.py"]) writeFileSync(join(repo, "tools", f), "");
  const runs = ["parts2m", "parts11s", "scene2"];
  writeFileSync(join(repo, "models.json"), JSON.stringify({
    version: "2026.11.07", release: "models-2026.11.07", default: ["parts2m", "parts11s"], scene: ["scene2"],
    files: Object.fromEntries(runs.map((r) => [r, { asset: `${r}.pt`, sha256: sha(r), bytes: r.length }])),
  }));
  const env = { LOCALAPPDATA: join(root, "Filippo Visentì") };
  if (install) {
    const dir = installDir(env);
    mkdirSync(join(dir, "venv", ...VENV_PYTHON, ".."), { recursive: true });
    writeFileSync(join(dir, "venv", ...VENV_PYTHON), "");
    mkdirSync(join(dir, "models", "2026.11.07"), { recursive: true });
    for (const r of runs) writeFileSync(join(dir, "models", "2026.11.07", `${r}.pt`), r);
    writeFileSync(join(dir, "setup.json"), JSON.stringify({ version: "2026.11.07", device: "cuda",
      verified: Object.fromEntries(runs.map((r) => [r, sha(r)])), selftest: "ok" }));
  }
  return { repo, env };
}

test("the allowed tools and what each runs", () => {
  assert.deepEqual(Object.keys(TOOLS).sort(), ["crop", "overlay", "photo3d", "rectify", "silhouette"]);
  const { repo, env } = world();
  const r = toolCommand(repo, env, "rectify", ["a.jpg", "1,2 3,4 5,6 7,8", "out.jpg"]);
  assert.equal(r.error, undefined);
  assert.deepEqual(r.args, ["-I", join(repo, "tools", "rectify.py"), "a.jpg", "1,2 3,4 5,6 7,8", "out.jpg"]);
  assert.ok(r.python.endsWith(join("venv", ...VENV_PYTHON)));
  const o = toolCommand(repo, env, "overlay", ["p.jpg", "s.json", "o.jpg"]);
  assert.deepEqual(o.args.slice(1, 3), [join(repo, "tools", "photo_tools.py"), "overlay"]);
  assert.equal(toolCommand(repo, env, "crop", []).args[2], "crop");
});

test("any other tool name is refused before anything runs", () => {
  const { repo, env } = world();
  for (const bad of ["../dev/train_data", "rectify.py", "", "__proto__", "constructor", "RECTIFY", "dev/facade_bench"]) {
    const r = toolCommand(repo, env, bad, []);
    assert.equal(r.python, undefined, bad);
    assert.match(r.error, /rectify, photo3d, silhouette, overlay, crop/, bad);
  }
});

test("without a detector Python it says to run the setup", () => {
  const { repo, env } = world({ install: false });
  assert.match(toolCommand(repo, env, "rectify", []).error, /node scripts\/setup\.mjs/);
});

test("arguments travel whole; offline; the installed scene model is handed over", () => {
  const { repo, env } = world();
  const photo = "C:\\Users\\Filippo Visentì\\a b.jpg";
  const r = toolCommand(repo, env, "silhouette", ["mask", photo, "out.png"]);
  assert.deepEqual(r.args.slice(2), ["mask", photo, "out.png"]);
  assert.equal(r.env.YOLO_OFFLINE, "1");
  assert.ok(r.env.RHINO_SCENE_WEIGHTS.endsWith("scene2.pt"));
  assert.ok(r.env.RHINO_SCENE_WEIGHTS.includes("Filippo Visentì"));
});

test("the command line refuses an unknown tool with exit code 2", async () => {
  const code = await new Promise((resolve) => {
    execFile(process.execPath, [join(repoRoot, "scripts", "run-tool.mjs"), "../dev/train_data"], { windowsHide: true },
      (err) => resolve(err ? err.code : 0));
  });
  assert.equal(code, 2);
});
