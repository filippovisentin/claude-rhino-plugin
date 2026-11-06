import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
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
