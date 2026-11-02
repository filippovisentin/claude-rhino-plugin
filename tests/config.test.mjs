import { test } from "node:test";
import assert from "node:assert/strict";
import { compareVersions } from "../scripts/find-router.mjs";
import { describe, findConflicts, isConflicting } from "../scripts/config-check.mjs";

test("version order: numeric core, then release above prerelease", () => {
  const sorted = ["0.3.0-rc1", "0.10.0", "0.3.0", "0.3.0-beta.1", "0.3.0-beta.10", "0.2.9"].sort(compareVersions).reverse();
  assert.deepEqual(sorted, ["0.10.0", "0.3.0", "0.3.0-rc1", "0.3.0-beta.10", "0.3.0-beta.1", "0.2.9"]);
});

test("community rhinomcp is a conflict", () => {
  assert.equal(isConflicting("rhino", { command: "uvx", args: ["rhinomcp"] }), true);
  assert.equal(isConflicting("cad", { command: "python", args: ["-m", "rhino_mcp"] }), true);
});

test("the official router and this plugin's launcher are not conflicts", () => {
  const router = "C:/Users/x/AppData/Roaming/McNeel/Rhinoceros/packages/8.0/Rhino-MCP-Platform/0.3.0/router/win-x64/rhino-mcp-router.exe";
  assert.equal(isConflicting("rhino", { command: router }), false);
  assert.equal(isConflicting("rhino", { command: "node", args: ["/p/scripts/launch-router.mjs"] }), false);
});

test("unrelated, malformed and remote entries", () => {
  assert.equal(isConflicting("github", { command: "npx", args: ["gh-mcp"] }), false);
  assert.equal(isConflicting("rhino", null), false);
  assert.equal(isConflicting("rhino-cloud", { type: "http", url: "https://example.test/mcp" }), true);
});

test("descriptions never include args", () => {
  const line = describe("rhino", { command: "C:/bin/npx.cmd", args: ["foo", "--api-key", "sk-secret"] });
  assert.equal(line, '"rhino" -> npx.cmd');
  const found = findConflicts({ mcpServers: { rhino: { command: "uvx", args: ["rhinomcp", "--token=abc"] } } });
  assert.deepEqual(found, ['user: "rhino" -> uvx']);
  assert.ok(!found.join().includes("abc"));
});
