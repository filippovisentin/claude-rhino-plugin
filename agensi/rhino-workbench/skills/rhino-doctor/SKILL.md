---
name: rhino-doctor
description: Diagnose and fix the connection between an AI agent and Rhino 8 through McNeel's Rhino-MCP-Platform and the claude-rhino-plugin runtime - missing tools, router not found, the classic "Invalid response frame length" clash with the community rhinomcp server, no running Rhino, photo helpers without Python - and set the runtime up when the user asks.
version: "0.2.0"
license: MIT
---

# Rhino connection doctor

Requires: Rhino 8; terminal access for the diagnostic script.

This skill brings doctor.md (what each finding means and what to do) and the pack's shared runtime.md (requirements, install, the three call levels).

1. List the Rhino tools the agent actually has. `build_model` and `check_model` present: the connection is complete. Only McNeel's tools (`run_python`, `get_context`...): modelling works through level 2 of runtime.md once `RUNTIME_ROOT` is verified; offer to switch the server to the runtime's launcher for the dedicated tools.
2. With terminal access and a verified `RUNTIME_ROOT`, run `node "RUNTIME_ROOT/scripts/doctor.mjs"` and fix the first FAIL or WARN with doctor.md.
3. If the runtime is not installed, follow "Install the runtime" in runtime.md, with the user's consent for every change to their configuration.
4. After a fix, confirm once with a read-only call (`get_context` or `list_slots`) and say what was verified and what was not.

Never switch off safe mode, delete other MCP entries, or download detector weights to make something work. Keep credentials and other servers' arguments out of the report.
