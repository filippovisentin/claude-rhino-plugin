// Finds running Rhino processes, so the doctor can tell "no Rhino" from "Rhino without its MCP
// server": the router lists only Rhinos whose RhinoAI MCP listener is up.
import { execFileSync } from "node:child_process";

// `tasklist /FO CSV /NH` prints one quoted row per process; with no match it prints a
// localised INFO line instead, which has no quoted pid column.
export function parseTasklist(out) {
  const pids = [];
  for (const line of String(out).split(/\r?\n/)) {
    const m = /^"[^"]*","(\d+)"/.exec(line.trim());
    if (m) pids.push(Number(m[1]));
  }
  return pids;
}

export function parsePgrep(out) {
  return String(out).split(/\s+/).filter((s) => /^\d+$/.test(s)).map(Number);
}

export function findRhinoPids() {
  try {
    if (process.platform === "win32") {
      return parseTasklist(execFileSync("tasklist", ["/FI", "IMAGENAME eq Rhino.exe", "/FO", "CSV", "/NH"],
        { encoding: "utf8", windowsHide: true, timeout: 10000 }));
    }
    if (process.platform === "darwin") {
      return parsePgrep(execFileSync("pgrep", ["-x", "Rhinoceros"], { encoding: "utf8", timeout: 10000 }));
    }
  } catch { /* pgrep exits 1 with no match; a missing tool means we cannot tell */ }
  return [];
}

export function noSlotAdvice(pids) {
  if (pids.length) {
    return `Rhino is running (pid ${pids.join(", ")}) but its MCP server is not started. In Rhino run MCPStart; ` +
      "to start it with Rhino every time, turn on Load MCP server at startup in the RhinoAI settings";
  }
  return "no running Rhino found. Start Rhino 8 with the Rhino-MCP-Platform plugin loaded (the router can also spawn one on demand)";
}
