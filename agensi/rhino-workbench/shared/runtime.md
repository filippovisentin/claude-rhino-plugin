# Runtime: what must be installed, and how to reach it

This pack is instructions. The geometry is built by the free, MIT-licensed claude-rhino-plugin runtime on the user's own PC, which Agensi does not install or host. Every skill of the pack shares this file.

## Requirements

- Rhino 8 with McNeel's Rhino-MCP-Platform package (in Rhino: `_PackageManager`, search for it).
- Node.js 18 or newer.
- The runtime from [filippovisentin/claude-rhino-plugin](https://github.com/filippovisentin/claude-rhino-plugin) (public), as a Claude Code plugin or as a local clone.
- An agent that can load Agensi and call the local Rhino MCP server in the same session. An image-capable agent for photos.
- Optional, for the photo helpers (straighten, zoomed crop, overlay, camera solve): [`uv`](https://docs.astral.sh/uv/getting-started/installation/), then once, from the runtime folder: `node scripts/setup.mjs --tools` (about 150 MB: numpy, Pillow, OpenCV; no GPU, no models).

Nothing in this pack grants access to trained detector weights; the runtime's detector is optional and its weights are not part of this product.

## Install the runtime (when the user asks for setup)

Claude Code:
```text
claude plugin marketplace add filippovisentin/claude-rhino-plugin
claude plugin install rhino@claude-rhino
```
Other MCP clients (Claude Desktop, Codex, Cursor): clone the repository, then add a local stdio server whose command is `node` with the argument `<clone>/scripts/launch-router.mjs`, in that client's own configuration format. Change the user's configuration only with their consent, never overwrite unrelated entries, and start a new session afterwards so the server loads. `node <clone>/scripts/doctor.mjs` checks the result.

`RUNTIME_ROOT` below is the folder that holds `scripts/launch-router.mjs` and `rhino/rhinospec/__init__.py`: the clone, or the installed plugin's folder (Claude Code keeps it under `~/.claude/plugins/`). Verify it exists before using it; never run a command with the literal word `RUNTIME_ROOT`, and never point it at an Agensi temporary folder.

## Calling the builder: three levels, in this order

1. **Dedicated tools.** If the Rhino server lists `build_model` and `check_model`, use them: `check_model` validates and plans a spec without touching Rhino, `build_model` builds it in one call and returns a one-line summary.
2. **Same builder through `run_python`.** If those two are missing but the server offers McNeel's `run_python`, and `RUNTIME_ROOT` is verified (the file `RUNTIME_ROOT/rhino/rhinospec/__init__.py` exists), build with the identical builder:
   ```python
   import sys; p = r'RUNTIME_ROOT\rhino'; p in sys.path or sys.path.insert(0, p)
   import rhinospec; print(rhinospec.run(r'''<spec json>''', __rhino_doc__))
   ```
   and validate without building with `print(rhinospec.check(r'''<spec json>'''))`. Replace `RUNTIME_ROOT` with the verified absolute path. This runs the user's own installed code, nothing from this pack. If the host asks for permission to run code, that is the user's choice; do not try to avoid the prompt.
3. **Neither.** No `build_model` and no usable `run_python` (missing, refused, or a server started in `--safe` mode, which hides `run_python` on purpose): load the rhino-doctor skill of this pack and fix the connection. Never switch safe mode off to get a build.

One build call per spec, never one call per object.

## What each feature needs

| Feature | Needs | Without it |
|---|---|---|
| Objects, buildings, facades, blocks, columns, stairs | level 1 or 2 above, an open Rhino document | rhino-doctor; no build is claimed |
| Reading a photo | an agent that can see the image | ask for dimensions in text |
| Viewport check | the server's `get_viewport_image` | say the visual check was not done |
| Straighten, crop, overlay, camera solve, silhouette compare | `node "RUNTIME_ROOT/scripts/run-tool.mjs" ...` and the light Python of `setup.mjs --tools` (or the detector's) | read the photo directly; say what was skipped |
| Building cut-out (`silhouette mask`) | a scene model of the detector setup | not available; use `photo3d` from read corners |
| Detector draft (`detect_facade`) | the tool listed by the server, with weights the user may use | read every element by hand (on test facades, hand reading scored about 0.5-0.8 mean overlap per element class) |

If `run-tool` says no Python is found, tell the user the one command: `node scripts/setup.mjs --tools` in `RUNTIME_ROOT`.
