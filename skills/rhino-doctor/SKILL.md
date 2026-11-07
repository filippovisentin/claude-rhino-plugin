---
name: rhino-doctor
description: Diagnose and fix the connection between Claude and Rhino 8. Use when Rhino MCP tools fail, time out, or are missing, when errors mention port 10500, "Could not connect to Rhino", "Invalid response frame length", "mcpstart", or when the user asks to connect Claude to Rhino or Grasshopper.
---

# Rhino doctor

This plugin runs McNeel's `rhino-mcp-router` (from the **Rhino-MCP-Platform** package) as the `rhino` MCP server. The router talks to Rhino over HTTP on `localhost:10500` and can adopt a running Rhino or spawn one.

## 1. Run the doctor

```bash
node "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.mjs"
```

Each line is `OK`, `WARN` or `FAIL`. Fix the first `FAIL` before looking at the rest.

## 2. Fixes by check

| Check | Problem | Fix |
|---|---|---|
| `node` | Node older than 18 | Install a current Node.js LTS. |
| `package` | Rhino-MCP-Platform missing | In Rhino run `_PackageManager`, install **Rhino-MCP-Platform**, restart Rhino. |
| `router` | No router executable | Reinstall the package, or set `RHINO_MCP_ROUTER` to the full path of `rhino-mcp-router(.exe)`. |
| `config` | Another Rhino MCP entry (often `uvx rhinomcp`) | That is the community plugin, which speaks a different protocol on the same port. Ask the user before removing it: `claude mcp remove <name> -s user` for `user:` lines, `-s local` (run in that project) for `local (project …)` lines, `-s project` for `project (….mcp.json)` lines. |
| `mcp` | Timeout, error response, or "cannot start router" | Run the router path from the doctor output by hand and read its stderr. An error response usually means the Rhino-MCP-Platform package and router versions differ: update the package and restart Rhino. |
| `rhino` | No running Rhino | Start Rhino 8. The router can also start one through its `spawn_slot` tool. |
| `detector` | INFO: `not installed (optional)` | Optional: everything else works without it. To add the facade detector, run `node scripts/setup.mjs` in the plugin folder (Windows with an NVIDIA GPU; `--cpu` for a PC without one). It needs `uv`, `gh` signed in, and about 8 GB free. Only the photo tools (rectify, crop, overlay, photo3d): `node scripts/setup.mjs --tools`, about 150 MB, no GPU, no models. |
| `detector` | WARN: `setup not finished` | The setup was interrupted. Run `node scripts/setup.mjs` again: it skips what is done. |
| `detector` | WARN: `models X < Y` | The plugin asks for newer models. Run `node scripts/setup.mjs` again: it downloads only the new weights. |
| `detector` | FAIL: `… sha256 mismatch` | A model file differs from `models.json` (corrupted or replaced). Run `node scripts/setup.mjs` again; it downloads and checks it anew. |
| `detector` | FAIL: `python … does not start` | The detector's Python is broken. Run `node scripts/setup.mjs` again: it rebuilds the venv under `%LOCALAPPDATA%\claude-rhino`. |
| `detector` | WARN: `gpu not available, running on CPU` | The detector still works, about 0.4 s per photo. For the GPU: update the NVIDIA driver (570 or newer) and restart; a `--cpu` install stays on the CPU until the setup is run without `--cpu`. |
| `detector` | Setup stops at `prereqs` | Follow its message: install the NVIDIA driver or use `--cpu`; install `uv`; `gh auth login`; ask to be added to the repository; free disk space. |
| `detector` | INFO: `using repo data/` or `using RHINO_FACADE_…` | Development PC or a manual override: nothing to fix. |

## Symptom: "Invalid response frame length 1213486160"

1213486160 is the bytes `HTTP` read as a length prefix. A socket-based client (the community `rhinomcp`) is talking to the HTTP server of Rhino-MCP-Platform. Remove or rename the conflicting entry; `mcpstart` will not help, because it belongs to the other plugin.

## Symptom: viewport image arrives as JSON text, or "exceeds maximum allowed tokens"

The router nests the image inside a text block. The plugin's launcher unwraps it, so this means the running `rhino` server predates plugin 0.2.0 or `RHINO_MCP_RAW=1` is set. Ask the user to start a new session. As a stopgap, capture to a file inside Rhino with `run_python` (`Rhino.Display.ViewCapture` → `bitmap.Save(path)`) and read that file.

## 3. Confirm

After changing MCP config, the user must start a new Claude session. Then call the `rhino` server's `list_slots` and `get_context` tools: they are read-only and confirm the live document.
