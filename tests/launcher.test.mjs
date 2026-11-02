import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const launcher = fileURLToPath(new URL("../scripts/launch-router.mjs", import.meta.url));
const fake = fileURLToPath(new URL("./fixtures/fake-router.mjs", import.meta.url));

function run(env = {}) {
  return new Promise((resolve) => {
    // RHINO_MCP_ROUTER = node itself; the launcher forwards its args, so the "router" is the fixture.
    const child = spawn(process.execPath, [launcher, fake], {
      env: { ...process.env, RHINO_MCP_ROUTER: process.execPath, ...env },
      stdio: ["pipe", "pipe", "pipe"],
    });
    let out = "";
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (d) => (out += d));
    child.on("close", (code) => resolve({ code, out }));
    child.stdin.write('{"jsonrpc":"2.0","id":1,"method":"ping"}\n');
  });
}

test("proxies every message through to the end, unwrapping nested images", async () => {
  const { code, out } = await run();
  assert.equal(code, 0);
  const lines = out.split("\n");
  const first = JSON.parse(lines[0]);
  assert.deepEqual(first.result.content, [
    { type: "text", text: "meta" },
    { type: "image", data: "QUJD", mimeType: "image/jpeg" },
  ]);
  assert.equal(lines[1], '{"jsonrpc":"2.0","id":2,"result":{}}\r', "plain lines keep their bytes");
  assert.equal(JSON.parse(lines[2]).result.content[0].text.length, 200_000);
  assert.equal(JSON.parse(lines[3]).result.content[0].text, "è last", "final line without newline survives exit");
});

test("RHINO_MCP_RAW=1 passes router output through untouched", async () => {
  const { out } = await run({ RHINO_MCP_RAW: "1" });
  const first = JSON.parse(out.split("\n")[0]);
  assert.equal(first.result.content.length, 1);
  assert.equal(first.result.content[0].type, "text");
});

test("reports a bad RHINO_MCP_ROUTER clearly", async () => {
  const child = spawn(process.execPath, [launcher], {
    env: { ...process.env, RHINO_MCP_ROUTER: "C:/nope/rhino-mcp-router.exe" },
    stdio: ["ignore", "ignore", "pipe"],
  });
  let err = "";
  child.stderr.on("data", (d) => (err += d));
  const code = await new Promise((r) => child.on("close", r));
  assert.equal(code, 1);
  assert.match(err, /RHINO_MCP_ROUTER points to a missing file/);
});
