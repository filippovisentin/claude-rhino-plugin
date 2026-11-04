# Claude panel for Rhino 8

A small chat panel inside Rhino 8, docked under the Layers panel. It sends your prompt to the AI command-line tool installed on your computer and shows the reply. That tool runs on your own plan, so there is no shared server and no API key:

| You have | The panel uses | Log in once with |
|---|---|---|
| a Claude plan | `claude` (Claude Code) | `claude`, then `/login` |
| a ChatGPT plan | `codex` (Codex) | `codex login` |

The panel passes this plugin's Rhino MCP server (`scripts/launch-router.mjs`) to the tool, so it can read and change the open model: `build_model`, `run_python`, `get_context` and the rest. It is told not to request viewport images unless you ask for one.

## Setup

1. Install the `Rhino-MCP-Platform` package (`_PackageManager`), Node.js, and `claude` and/or `codex`. Log in to the tool you want to use.
2. In Rhino, run once:

   ```
   _-RunPythonScript "C:\path\to\claude-rhino-plugin\rhino\panel\claude_panel.py"
   ```

   This adds a `ClaudePanel` command alias and opens the panel under Layers.
3. Afterwards type `ClaudePanel` to show or hide it.

The panel is a normal Rhino panel: drag its tab to dock it somewhere else, float it, or close it. Rhino remembers where you put it.

## Using it

- Pick **Claude** or **ChatGPT** from the drop-down. Only the tools that are installed appear.
- Press Enter to send and Shift+Enter for a new line. **Stop** cancels a reply, and **Nuova** starts a new conversation.
- Tool calls show up as `· build_model` lines, so you can see what was done to the model.
- Each panel conversation is a normal Claude Code or Codex session, so follow-up questions keep their context.

If the tool is not found because Rhino was started with a different `PATH`, set `CLAUDE_PANEL_CLAUDE` or `CLAUDE_PANEL_CODEX` to the full path of the executable.

## How it works

- `claude_panel_core.py` is plain Python with no Rhino imports. It finds the CLI, builds the command line and runs one turn on a worker thread, reading the CLI's JSON event stream. The prompt goes in on stdin. The MCP config and system prompt are written to `%LOCALAPPDATA%\claude-rhino-panel\`, which is also the CLI's working folder.
- `claude_panel.py` contains the Eto UI and the Rhino integration. Rhino's panel system needs a .NET type with a `GuidAttribute`, which a Python class cannot carry, so the script creates a small `Eto.Forms.Panel` subclass with `Reflection.Emit` once per session, and its constructor calls back into Python to build the content.
- RhinoCommon can open a panel in a new dock bar, but it cannot place that bar under another one. To stack the bar under Layers on first open, the script uses Rhino 8's internal dock-site classes (`Rhino.UI.Internal.TabPanels`). If a later Rhino version changes them, the panel stays where Rhino puts it and you can drag it into place.

Tests: `python -m unittest tests.test_panel` (part of `npm run test:py`).
