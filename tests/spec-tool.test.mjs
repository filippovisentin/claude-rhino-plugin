import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { createSpecBridge, extractSummary, pythonScript, TOOLS } from "../scripts/spec-tool.mjs";

const rhinoDir = fileURLToPath(new URL("../rhino", import.meta.url));
const table = { units: "m", parts: [{ type: "box", size: [1, 1, 1] }] };

test("adds build_model and check_model to the router's tool list", () => {
  const b = createSpecBridge(rhinoDir);
  const req = '{"jsonrpc":"2.0","id":7,"method":"tools/list"}';
  assert.equal(b.fromClient(req).toRouter, req);
  const reply = JSON.parse(b.fromRouter('{"jsonrpc":"2.0","id":7,"result":{"tools":[{"name":"run_python"}]}}'));
  assert.deepEqual(reply.result.tools.map((t) => t.name), ["run_python", "build_model", "check_model"]);
  assert.equal(b.pending.size, 0);
});

test("rewrites build_model into run_python with base64-only inputs", () => {
  const b = createSpecBridge(rhinoDir);
  const evil = { units: "m", layer: "x\"\"\")\nimport os; os.system('calc')#", parts: [] };
  const { toRouter } = b.fromClient(JSON.stringify({
    jsonrpc: "2.0", id: "a1", method: "tools/call", params: { name: "build_model", arguments: { spec: evil, slot: "s1" } },
  }));
  const msg = JSON.parse(toRouter);
  assert.equal(msg.id, "a1");
  assert.equal(msg.params.name, "run_python");
  assert.equal(msg.params.arguments.slot, "s1");
  const script = msg.params.arguments.script;
  assert.ok(!script.includes("os.system") && !script.includes("calc"), "spec text never appears in the script");
  assert.match(script, /rhinospec\.run\(s, __rhino_doc__\)/);
});

test("rejects bad slots and missing or oversized specs without calling the router", () => {
  const b = createSpecBridge(rhinoDir);
  const call = (args) => b.fromClient(JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name: "build_model", arguments: args } }));
  assert.match(call({ spec: table, slot: "../x y" }).toClient, /bad slot/);
  assert.match(call({}).toClient, /spec is required/);
  assert.match(call({ spec: "x".repeat(1_000_001) }).toClient, /larger than 1 MB/);
  assert.equal(b.pending.size, 0);
});

test("other tools and router requests pass through untouched", () => {
  const b = createSpecBridge(rhinoDir);
  const other = '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"run_python","arguments":{"script":"print(1)"}}}';
  assert.equal(b.fromClient(other).toRouter, other);
  b.fromClient('{"jsonrpc":"2.0","id":3,"method":"tools/list"}');
  const routerRequest = '{"jsonrpc":"2.0","id":3,"method":"elicitation/create","params":{}}';
  assert.equal(b.fromRouter(routerRequest), routerRequest);
});

test("trims run_python replies to the summary line and flags failures", () => {
  const b = createSpecBridge(rhinoDir);
  b.fromClient(JSON.stringify({ jsonrpc: "2.0", id: 5, method: "tools/call", params: { name: "build_model", arguments: { spec: table } } }));
  const payload = 'Creating meshes... Press Esc to cancel\nRHINOSPEC {"ok":false,"error":"parts[0].size: x"}\n';
  const routerReply = { jsonrpc: "2.0", id: 5, result: { content: [{ type: "text", text: JSON.stringify({ payload }) }] } };
  const out = JSON.parse(b.fromRouter(JSON.stringify(routerReply)));
  assert.deepEqual(out.result.content, [{ type: "text", text: '{"ok":false,"error":"parts[0].size: x"}' }]);
  assert.equal(out.result.isError, true);
});

test("finds the summary in either payload shape", () => {
  const line = 'RHINOSPEC {"ok":true,"added":3}';
  assert.equal(extractSummary({ payload: "noise\n" + line }), '{"ok":true,"added":3}');
  assert.equal(extractSummary({ content: [{ type: "text", text: JSON.stringify({ payload: line }) }] }), '{"ok":true,"added":3}');
  assert.equal(extractSummary({ content: [{ type: "text", text: "nothing" }] }), null);
});

test("the generated script really runs (check path, local Python, no Rhino)", (t) => {
  const py = spawnSync("python", ["--version"]);
  if (py.status !== 0) return t.skip("python not on PATH");
  const quoted = { units: "m", layer: "a'''b", parts: [{ type: "box", size: [1, 1, 1] }] };
  for (const [spec, expectOk] of [[table, true], [quoted, false]]) {
    const r = spawnSync("python", ["-I", "-c", pythonScript(rhinoDir, JSON.stringify(spec), "check")], { encoding: "utf8" });
    assert.equal(r.status, 0, r.stderr);
    const summary = JSON.parse(r.stdout.trim().replace(/^RHINOSPEC /, ""));
    assert.equal(summary.ok, expectOk);
  }
});

test("tool descriptions stay compact", () => {
  for (const tool of TOOLS) assert.ok(tool.description.length < 2600, `${tool.name}: ${tool.description.length} chars`);
});

test("safe mode lists and allows only modelling and read tools", () => {
  const b = createSpecBridge(rhinoDir, { safe: true });
  assert.equal(b.fromClient('{"jsonrpc":"2.0","id":1,"method":"tools/list"}').toRouter !== undefined, true);
  const router = { jsonrpc: "2.0", id: 1, result: { tools: ["run_python", "run_csharp", "run_command", "get_context",
    "g1_apply_graph", "save_doc", "open_doc", "spawn_slot", "build_model"].map((name) => ({ name, description: "router" })) } };
  const listed = JSON.parse(b.fromRouter(JSON.stringify(router))).result.tools;
  assert.deepEqual(listed.map((t) => t.name), ["get_context", "build_model", "check_model"]);
  assert.notEqual(listed[1].description, "router"); // ours, not a router tool of the same name

  for (const name of ["run_python", "run_csharp", "run_command", "g1_apply_graph", "save_doc", "spawn_slot"]) {
    const r = b.fromClient(JSON.stringify({ jsonrpc: "2.0", id: 2, method: "tools/call", params: { name, arguments: {} } }));
    assert.equal(r.toRouter, undefined, name);
    assert.match(JSON.parse(r.toClient).result.content[0].text, /disabled in safe mode/);
  }
  const ok = b.fromClient(JSON.stringify({ jsonrpc: "2.0", id: 3, method: "tools/call", params: { name: "get_context", arguments: {} } }));
  assert.ok(ok.toRouter);
  const built = JSON.parse(b.fromClient(JSON.stringify({ jsonrpc: "2.0", id: 4, method: "tools/call",
    params: { name: "build_model", arguments: { spec: { parts: [] } } } })).toRouter);
  assert.equal(built.params.name, "run_python"); // our fixed script still runs
});

test("safe mode cannot be bypassed with escapes, batches or junk", () => {
  const b = createSpecBridge(rhinoDir, { safe: true });
  const escaped = '{"jsonrpc":"2.0","id":5,"method":"tools\u002fcall","params":{"name":"run_\u0070ython","arguments":{"script":"x"}}}';
  const r = b.fromClient(escaped);
  assert.equal(r.toRouter, undefined);
  assert.match(JSON.parse(r.toClient).result.content[0].text, /disabled in safe mode/);
  const batch = JSON.stringify([{ jsonrpc: "2.0", id: 6, method: "tools/call", params: { name: "run_python", arguments: {} } }]);
  assert.deepEqual(b.fromClient(batch), { toClient: null });
  assert.deepEqual(b.fromClient("not json"), { toClient: null });
  // Normal mode keeps passing everything else through untouched.
  assert.equal(createSpecBridge(rhinoDir).fromClient(batch).toRouter, batch);
});
