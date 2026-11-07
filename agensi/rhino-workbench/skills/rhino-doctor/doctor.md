# Rhino connection diagnostics

Diagnose the existing local runtime; this is not an installer. Use the host's actual tool names and configuration format.

## First checks

If the configured server exposes `list_slots` and `get_context`, use their schemas for a read-only connection/document check. When several slots or documents are plausible, confirm the intended one. Their absence under safe mode is not proof of server failure: use available read-only context tools instead.

If terminal access and a verified runtime folder are available, run the existing diagnostic script:
```text
node "RUNTIME_ROOT/scripts/doctor.mjs"
```
Replace the symbolic root with the user's installation. No diagnostic script is delivered inside this skill. Its OK/WARN/FAIL lines are evidence; repair the first relevant failure.

## Findings and next steps

| Observation | Interpretation / action |
|---|---|
| Node older than 18 | Base runtime prerequisite missing; point to Node's official installation instructions |
| Rhino-MCP-Platform missing | In Rhino, PackageManager can install the McNeel package; have the user perform installation or obtain authorization before making local setup changes |
| Router executable missing | Verify installed package and runtime paths; a custom router path can be configured through the documented RHINO_MCP_ROUTER setting |
| Another server uses community `uvx rhinomcp` | It uses a different protocol. Inspect the actual conflict; do not delete entries or applications without resolving the user's intent |
| Invalid response frame length 1213486160 | The bytes spell HTTP being parsed as a socket length. Check community-client versus McNeel-HTTP mismatch; do not treat blindly running mcpstart as the cure |
| Router/package mismatch or timeout | Check versions, process stderr and the existing endpoint; reconnect after an authorized change |
| No live Rhino document | Ask the user to open the intended Rhino document, or use a supported launch tool only within the requested scope |
| Standard Rhino tools exist but build_model/check_model do not | The host runs McNeel's router directly or an older runtime. Modelling still works through level 2 of runtime.md (`run_python` with the verified runtime). To get the dedicated tools, point the Rhino entry at `RUNTIME_ROOT/scripts/launch-router.mjs`, with the user's consent |
| Viewport returned as JSON text | Verify the extension launcher is in use and raw mode is not deliberately enabled. Reconnect. Use an existing supported image route if available |
| Detector absent | Optional. Continue manual reading; do not install restricted studio weights |
| `run-tool` says no Python for the plugin's tools | Run `node scripts/setup.mjs --tools` in `RUNTIME_ROOT` (needs `uv`; about 150 MB, no models). Never fetch detector weights to fix it |
| Hash mismatch in a separately licensed detector setup | Do not use changed weights. Refer to the installation's verification/repair procedure; do not bypass the hash check |

After a correction, recheck the active document once through available read-only tools. Report what was observed versus what remains unverified. Keep credentials, command arguments containing secrets and unrelated environment variables out of reports.
