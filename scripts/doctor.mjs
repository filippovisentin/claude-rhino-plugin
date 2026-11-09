// Diagnoses the Claude <-> Rhino MCP connection and prints one line per check.
// Usage: node doctor.mjs [--json]
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { findInstalls, findRouter, packagesRoots } from "./find-router.mjs";
import { findConflicts, isConflicting, describe } from "./config-check.mjs";
import { detectorReport } from "./detector-install.mjs";
import { findRhinoPids, noSlotAdvice } from "./rhino-process.mjs";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";

const results = [];
const report = (status, check, detail) => results.push({ status, check, detail });
const readJson = (file) => {
  try {
    return existsSync(file) ? JSON.parse(readFileSync(file, "utf8")) : null;
  } catch {
    return null;
  }
};

// 1. Node
const major = parseInt(process.versions.node, 10);
report(major >= 18 ? "ok" : "fail", "node", `v${process.versions.node}${major >= 18 ? "" : " (need >= 18)"}`);

// 2. Package installs
const installs = findInstalls();
if (installs.length === 0) {
  report("fail", "package", `Rhino-MCP-Platform not installed (searched ${packagesRoots().join(", ") || "unsupported OS"}). Install it from Rhino: _PackageManager`);
} else {
  report("ok", "package", installs.map((i) => `${i.version} (Rhino ${i.rhino})`).join(", "));
}

// 3. Router executable
const router = findRouter();
if (router) report("ok", "router", router);
else report("fail", "router", process.env.RHINO_MCP_ROUTER ? `RHINO_MCP_ROUTER points to a missing file: ${process.env.RHINO_MCP_ROUTER}` : "no router executable inside the installed package");

// 4. Conflicting MCP entries: user and local scope in ~/.claude.json, project scope in ./.mcp.json
const conf = findConflicts(readJson(join(homedir(), ".claude.json")));
const projectMcp = readJson(join(process.cwd(), ".mcp.json"));
for (const [name, s] of Object.entries(projectMcp?.mcpServers ?? {})) {
  if (isConflicting(name, s)) conf.push(`project (${join(process.cwd(), ".mcp.json")}): ${describe(name, s)}`);
}
if (conf.length) report("warn", "config", `other Rhino MCP entries may shadow or conflict with this plugin:\n    ${conf.join("\n    ")}`);
else report("ok", "config", "no conflicting Rhino MCP entries");

// 4b. Optional local facade detector (detect_facade): installed by scripts/setup.mjs, or the repo's data/
for (const r of await detectorReport(dirname(dirname(fileURLToPath(import.meta.url))))) report(r.status, r.check, r.detail);

// 5. Live handshake through the router: list_slots shows running Rhino instances
function handshake() {
  return new Promise((done) => {
    const child = spawn(router, [], { stdio: ["pipe", "pipe", "ignore"], windowsHide: true });
    const pending = new Map();
    let buf = "";
    let id = 0;
    const finish = (status, detail) => {
      if (status) report(status, "mcp", detail);
      for (const reject of pending.values()) reject(new Error("router exited"));
      pending.clear();
      child.kill();
      done();
    };
    child.on("error", (e) => finish("fail", `cannot start router: ${e.message}`));
    child.on("exit", () => pending.size && finish("fail", "router exited during the handshake"));
    child.stdin.on("error", () => {});
    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (d) => {
      buf += d;
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        let m;
        try { m = JSON.parse(line); } catch { continue; } // non-JSON noise
        const cb = pending.get(m.id);
        if (cb) { pending.delete(m.id); cb(m); }
      }
    });
    const rpc = (method, params) =>
      new Promise((res, rej) => {
        const myId = ++id;
        const t = setTimeout(() => rej(new Error(`timeout waiting for ${method}`)), 20000);
        pending.set(myId, (m) => {
          clearTimeout(t);
          if (m instanceof Error) return rej(m);
          if (m.error) return rej(new Error(`${method}: ${m.error.message ?? JSON.stringify(m.error)}`));
          res(m.result);
        });
        child.stdin.write(JSON.stringify({ jsonrpc: "2.0", id: myId, method, params }) + "\n");
      });
    (async () => {
      try {
        const init = await rpc("initialize", { protocolVersion: "2025-06-18", capabilities: {}, clientInfo: { name: "claude-rhino-doctor", version: "1" } });
        child.stdin.write(JSON.stringify({ jsonrpc: "2.0", method: "notifications/initialized" }) + "\n");
        const tools = await rpc("tools/list", {});
        report("ok", "mcp", `${init?.serverInfo?.name} ${init?.serverInfo?.version}, ${tools?.tools?.length ?? 0} tools`);
        const slots = await rpc("tools/call", { name: "list_slots", arguments: {} });
        let payload = [];
        try { payload = JSON.parse(slots?.content?.[0]?.text ?? "").payload ?? []; } catch { /* keep empty */ }
        if (payload.length) report("ok", "rhino", payload.map((s) => `Rhino ${s.version} pid ${s.pid} at ${s.endpoint}`).join("; "));
        else report("warn", "rhino", noSlotAdvice(findRhinoPids()));
        finish(null);
      } catch (e) {
        finish("fail", e.message);
      }
    })();
  });
}
if (router) await handshake();

if (process.argv.includes("--json")) {
  console.log(JSON.stringify(results, null, 2));
} else {
  const tag = { ok: "OK  ", warn: "WARN", fail: "FAIL", info: "INFO" };
  for (const r of results) console.log(`[${tag[r.status]}] ${r.check.padEnd(8)} ${r.detail}`);
}
process.exitCode = results.some((r) => r.status === "fail") ? 1 : 0;
