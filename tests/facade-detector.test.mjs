import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, mkdirSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { createSpecBridge } from "../scripts/spec-tool.mjs";
import { checkConf, checkImage, findDetector, runDetector } from "../scripts/facade-detector.mjs";

const rhinoDir = fileURLToPath(new URL("../rhino", import.meta.url));
const dir = mkdtempSync(join(tmpdir(), "facade-det-"));
const photo = join(dir, "front.jpg");
writeFileSync(photo, "jpeg");
const det = { python: "py", weights: "w.pt", script: "facade_yolo.py", configDir: null };
const call = (id, args) => JSON.stringify({ jsonrpc: "2.0", id, method: "tools/call", params: { name: "detect_facade", arguments: args } });
const draft = '{"img":[10,20],"els":[{"k":"window","box":[1,2,3,4]}],"review":"r"}';

test("detect_facade is listed only when a detector is installed", () => {
  const list = (b) => {
    b.fromClient('{"jsonrpc":"2.0","id":1,"method":"tools/list"}');
    return JSON.parse(b.fromRouter('{"jsonrpc":"2.0","id":1,"result":{"tools":[]}}')).result.tools.map((t) => t.name);
  };
  assert.ok(!list(createSpecBridge(rhinoDir)).includes("detect_facade"));
  assert.ok(list(createSpecBridge(rhinoDir, { detector: det })).includes("detect_facade"));
  assert.ok(list(createSpecBridge(rhinoDir, { safe: true, detector: det })).includes("detect_facade"));
  const r = createSpecBridge(rhinoDir).fromClient(call(1, { image: photo }));
  assert.match(JSON.parse(r.toClient).result.content[0].text, /no trained detector/);
});

test("runs locally with the path as one argv entry, never through the router or a shell", async () => {
  const seen = [];
  const run = (file, args, opts, cb) => { seen.push({ file, args, opts }); cb(null, "ultralytics noise\n" + draft + "\n"); };
  const b = createSpecBridge(rhinoDir, { safe: true, detector: det, run });
  const r = b.fromClient(call("d1", { image: photo, conf: 0.3 }));
  assert.equal(r.toRouter, undefined);
  const reply = JSON.parse(await r.local);
  assert.equal(reply.id, "d1");
  assert.deepEqual(JSON.parse(reply.result.content[0].text).img, [10, 20]);
  assert.equal(seen[0].file, "py");
  assert.deepEqual(seen[0].args.slice(0, 3), ["-I", "facade_yolo.py", "detect-image"]);
  assert.equal(seen[0].args[4], "w.pt");
  assert.equal(seen[0].args[5], "0.3");
  assert.equal(seen[0].opts.shell, false);
  assert.ok(seen[0].opts.timeout > 0 && seen[0].opts.maxBuffer > 0);
});

test("detector failures and junk output become tool errors", async () => {
  const fail = createSpecBridge(rhinoDir, { detector: det, run: (f, a, o, cb) => cb(Object.assign(new Error("x"), { killed: true })) });
  assert.match(JSON.parse(await fail.fromClient(call(2, { image: photo })).local).result.content[0].text, /timed out/);
  const junk = createSpecBridge(rhinoDir, { detector: det, run: (f, a, o, cb) => cb(null, "not json") });
  const out = JSON.parse(await junk.fromClient(call(3, { image: photo })).local);
  assert.equal(out.result.isError, true);
  assert.match(out.result.content[0].text, /no draft/);
});

test("rejects bad image paths and confidences before running anything", () => {
  let ran = false;
  const b = createSpecBridge(rhinoDir, { detector: det, run: () => { ran = true; } });
  const folder = join(dir, "pics.jpg");
  mkdirSync(folder);
  const notes = join(dir, "notes.txt");
  writeFileSync(notes, "x");
  for (const [args, why] of [
    [{}, /must be a path/], [{ image: "front.jpg" }, /absolute/], [{ image: notes }, /jpg, png/],
    [{ image: join(dir, "missing.jpg") }, /not found/], [{ image: folder }, /not a file/],
    [{ image: photo + "\0.jpg" }, /must be a path/], [{ image: photo, conf: 2 }, /conf/], [{ image: photo, conf: "0.3" }, /conf/],
  ]) {
    const r = b.fromClient(call(4, args));
    assert.equal(r.local, undefined, JSON.stringify(args));
    assert.match(JSON.parse(r.toClient).result.content[0].text, why);
  }
  assert.equal(ran, false);
});

test("a link to a non-image is refused by its real target", (t) => {
  const link = join(dir, "link.jpg");
  try { symlinkSync(join(dir, "notes.txt"), link); } catch { return t.skip("no symlink permission"); }
  assert.throws(() => checkImage(link), /jpg, png/);
});

test("helpers: defaults and detector discovery", () => {
  assert.equal(checkConf(undefined), 0.25);
  assert.equal(findDetector(dir, {}), null);
  const py = join(dir, "py.exe"), w = join(dir, "w.pt");
  writeFileSync(py, ""); writeFileSync(w, "");
  mkdirSync(join(dir, "tools"));
  writeFileSync(join(dir, "tools", "facade_yolo.py"), "");
  const found = findDetector(dir, { RHINO_FACADE_PYTHON: py, RHINO_FACADE_WEIGHTS: w });
  assert.equal(found.python, py);
  assert.equal(found.weights, w);
});

test("runDetector reads the last stdout line", async () => {
  const text = await runDetector(det, photo, 0.25, (f, a, o, cb) => cb(null, "a\nb\n" + draft));
  assert.equal(JSON.parse(text).els.length, 1);
});
