// Finds MCP server entries that would clash with this plugin's "rhino" server, e.g. the community
// `uvx rhinomcp` package, which speaks a different protocol on the same port.
import { basename } from "node:path";

// True when an entry looks like a non-official Rhino MCP server.
export function isConflicting(name, server) {
  if (!server || typeof server !== "object") return false;
  const parts = [server.command, ...(Array.isArray(server.args) ? server.args : []), server.url]
    .filter((x) => typeof x === "string");
  // The official router (and this plugin's launcher) are never a conflict.
  const line = parts.join(" ").replace(/rhino-mcp-(router|platform)|launch-router\.mjs/gi, "");
  if (/rhinomcp|rhino[_-]mcp/i.test(line)) return true;
  if (!/rhino/i.test(name)) return false;
  // A Rhino-named entry that runs neither the router nor our launcher.
  const full = parts.join(" ");
  return !/rhino-mcp-router|launch-router\.mjs/i.test(full);
}

// What the doctor may print about an entry: name and executable basename only, never args or
// env, which can hold API keys.
export function describe(name, server) {
  const cmd = typeof server?.command === "string" ? basename(server.command) : server?.url ? "(remote url)" : "(no command)";
  return `"${name}" -> ${cmd}`;
}

export function findConflicts(cfg) {
  const found = [];
  const scan = (servers, scope) => {
    if (!servers || typeof servers !== "object") return;
    for (const [name, s] of Object.entries(servers)) {
      if (isConflicting(name, s)) found.push(`${scope}: ${describe(name, s)}`);
    }
  };
  scan(cfg?.mcpServers, "user");
  for (const [path, proj] of Object.entries(cfg?.projects ?? {})) scan(proj?.mcpServers, `local (project ${path})`);
  return found;
}
