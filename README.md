# claude-rhino

A Claude Code plugin that connects Claude to **Rhino 8** (and Grasshopper) through McNeel's official **Rhino-MCP-Platform** router.

**New here? Read the three-page overview, written for designers: [docs/rhino-plugin-overview.pdf](docs/rhino-plugin-overview.pdf)**

It adds:

- **`rhino` MCP server**: a small Node launcher that finds the newest installed `rhino-mcp-router` and runs it over stdio. No version-specific paths in your config, so Rhino package updates don't break it.
- **Viewport images Claude can actually see**: router 0.3.0 returns `get_viewport_image` as one big JSON text block with the image inside it, so Claude gets text instead of a picture, and larger captures exceed the tool-output limit. The launcher unwraps those results into real MCP image content. It only does so when the nested content holds an image, and it rebuilds each item from known fields (`text`, or `image` with an `image/*` type and base64 data), so document text can't turn itself into links or annotations. Every other message passes through unchanged.
- **`build_model` and `check_model` tools**: the launcher adds them to the router's tool list. They take a JSON spec, rewrite the call into McNeel's `run_python` with the spec and paths base64-encoded inside a fixed script (nothing the model writes becomes Python), and trim the reply to one summary line.
- **`rhino-model` skill (text, prompt or image to 3D)**: Claude writes a compact JSON spec (boxes, cylinders, revolves, lofts, pipes, arrays, boolean cuts, and whole buildings with floors, openings and roofs) and the `rhinospec` builder in [`rhino/`](rhino/rhinospec) turns it into solids with one `run_python` call. A spec costs far fewer tokens than RhinoCommon code, cannot run arbitrary code, is strictly validated (known keys only, finite numbers, 2000-part limit), and only ever writes to and clears sublayers of `rhinospec`. For photos of elevations, a `facade` part takes pixel boxes read straight off the image (windows, doors, shop fronts, cornices, mouldings, sills, pillars, balconies, shutters, ornaments) and builds the wall with real openings, frames, glass, glazing bars and projections. A `block` part is a whole rectangular building with one such facade per side, for corner buildings or several photos of one building, with layers per side (Front/Right/Back/Left).
- **`rhino-doctor` skill**: a diagnostic script plus a fix table for connection problems, including the classic clash with the community `rhinomcp` package.

> Unofficial. This plugin only launches the router that ships with McNeel's Rhino-MCP-Platform package; it doesn't include or modify it.

## Requirements

- Rhino 8 with the **Rhino-MCP-Platform** package (in Rhino: `_PackageManager`, then search for it)
- Node.js 18 or newer on `PATH`
- Claude Code

Tested on Windows 11 (x64) with Rhino-MCP-Platform 0.3.0. The macOS path lookup is written but not yet tested.

## Install

```bash
claude plugin marketplace add filippovisentin/claude-rhino-plugin
claude plugin install rhino@claude-rhino
```

From a local clone:

```bash
claude plugin marketplace add ./claude-rhino-plugin
claude plugin install rhino@claude-rhino
```

Start a new Claude session afterwards so the MCP server loads.

### Other MCP clients (your own Claude or ChatGPT plan)

The `rhino` server is a plain stdio MCP server, so it works with any client that runs local MCP servers, on that client's own plan. It exposes McNeel's tools plus `build_model` and `check_model`, whose descriptions carry the spec, so clients without Claude Code skills can use them too. Replace the path with your clone.

Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "rhino": { "command": "node", "args": ["C:/path/to/claude-rhino-plugin/scripts/launch-router.mjs"] } } }
```

Codex CLI, with a ChatGPT plan (`~/.codex/config.toml`):

```toml
[mcp_servers.rhino]
command = "node"
args = ["C:/path/to/claude-rhino-plugin/scripts/launch-router.mjs"]
```

Cursor and other clients take the same command and arguments. The ChatGPT desktop and web apps only connect to remote (HTTPS) MCP servers, so they can't launch this local server directly; use Codex with your ChatGPT plan instead.

## Check the connection

```bash
node scripts/doctor.mjs
```

```
[OK  ] node     v24.15.0
[OK  ] package  0.3.0 (Rhino 8.0)
[OK  ] router   C:\Users\you\AppData\Roaming\McNeel\...\rhino-mcp-router.exe
[OK  ] config   no conflicting Rhino MCP entries in ~/.claude.json
[OK  ] mcp      rhino-mcp-router 0.3.0, 32 tools
[OK  ] rhino    Rhino 8 pid 54748 at http://localhost:10500
```

Or just ask Claude: *"Rhino isn't connecting"*. The `rhino-doctor` skill runs the same check.

## Troubleshooting

**`Invalid response frame length 1213486160`**: 1213486160 is the ASCII bytes `HTTP`. Your config runs the community `rhinomcp` (socket protocol) against the Rhino-MCP-Platform HTTP server on port 10500. Remove the old entry:

```bash
claude mcp remove rhino -s user
```

**Router in a non-standard place**: set `RHINO_MCP_ROUTER` to the full path of `rhino-mcp-router(.exe)`.

**Viewport image shows up as text**: you are on plugin 0.1.x, or the session started before the update. Start a new Claude session. To compare with the router's unmodified output, set `RHINO_MCP_RAW=1`.

## Security notes

- The router's `run_python`, `run_csharp` and `run_command` tools run arbitrary code inside Rhino. That is their purpose; keep Claude Code's permission prompts on for them unless you trust the session.
- Text from Rhino documents (object names, user text, files from others) reaches Claude through tool results. Treat models from untrusted sources like any untrusted input.
- `doctor.mjs` prints only the name and executable of other MCP entries, never their arguments or environment, since those can hold API keys.
- Open questions about McNeel's closed-source router and Rhino's HTTP listener on `localhost:10500`, not answerable from this repository: whether it checks `Origin` against browser requests, whether router and Rhino share a secret, and whether the router verifies it is talking to the real Rhino if another process takes the port first.

## Development

```bash
npm test
```

Runs `node --test` (result unwrapping, version ordering, config conflicts, launcher framing) and the Python `unittest` suite for the rhinospec validator and building planner (`npm run test:py`). Both need no dependencies; the Rhino builder itself is checked by building the examples in `skills/rhino-model/SKILL.md` in a live Rhino.

## Facade benchmark

`tools/facade_bench.py` measures image-to-3D on the [CMP Facade Database](https://cmp.felk.cvut.cz/~tylecr1/facade/) (606 annotated facades, CC BY-SA, Tyleček & Šára, GCPR 2013). The dataset isn't in the repository: download and unzip it into `data/cmp/` (ignored by git).

```bash
python tools/facade_bench.py prep cmp_b0101                         # resized photo to read
python tools/facade_bench.py score cmp_b0101 data/work/pred.json    # per-class IoU against the annotation
python tools/facade_bench.py gt cmp_b0101                           # annotation as a facade spec
```

All 606 annotations, converted to specs, build in Rhino without errors (about 0.1 s and 125 solids per facade). `tools/fuzz_specs.py N SEED OUT` writes random valid specs (every primitive, arches, pediments, volumes, cuts, mm/cm/m); 800 of them, about 125,000 solids, build with no geometry failures. `tools/clean_pick.py N` ranks the photos by how clean the facade is (little vegetation, facade filling the frame, regular windows), which is the easiest set to start from. `tools/facade_refine.py` (template matching and edge snapping) is experimental: on the photos measured so far it lowered accuracy, see its docstring.

Readings by Claude, scored in photo pixels (window IoU / all openings / mean over classes):

| photo | kind | windows | openings | mean |
|---|---|---|---|---|
| cmp_b0161 | clean, 7 floors, balconies | 0.80 | 0.80 | 0.77 |
| cmp_b0033 | clean, arched portal, hoods | 0.78 | 0.79 | 0.51 |
| cmp_b0290 | clean, balconies, shutters | 0.77 | 0.77 | 0.47 |
| cmp_b0101 | historic, ornaments | 0.87 | 0.78 | 0.36 |
| cmp_b0304 | trees in front | 0.61 | 0.61 | 0.40 |
| cmp_b0069 | clean, shopfronts | 0.76 | 0.87 | 0.61 |
| cmp_b0186 | clean, ornate, arches, pediments | 0.85 | 0.76 | 0.55 |
| cmp_b0189 | warped into a street-level perspective, then straightened with `tools/rectify.py` from four read corners | 0.80 | 0.80 | 0.61 |

### Ordinary photos

`tools/photo_bench.py` scores readings of people's street photos, perspective and clutter included, against [LabelMeFacade](https://github.com/cvjena/labelmefacade) (945 LabelMe photos with window/door label maps, research use only; Fröhlich, Rodner, Denzler, ICPR 2010) and [hznu_facade](https://data.mendeley.com/datasets/k387xkyc5f/1) (624 Hangzhou photos with window/door polygons and ground-truth homographies, CC BY 4.0). Download them into `data/labelmefacade` and `data/hznu`. When a photo was straightened first (`photo_bench.py rect`), the boxes read on the straight image are projected back through the inverse homography, so the score covers the whole chain: corners, straightening, reading.

| photo | how it was read | windows | door | openings |
|---|---|---|---|---|
| London pub front, steep angle, signs and flower baskets | four corners, straightened, then read | 0.90 | not annotated | 0.78 |
| Boston house with a bay, mild perspective | read directly | 0.86 | 0.67 | 0.83 |
| hznu c_0174, 13-storey tower from street level, 179 windows | four corners, straightened, uniform row step | 0.56 | | 0.56 |
| hznu d_0112, drone view, 182 windows of 20 px | read directly with `xs`/`ys` | 0.48 | | 0.48 |
| hznu c_0075, 7-storey slab seen across its corner from below | `block`: front face straightened and read, blank side a plain wall | 0.81 | | 0.81 |
| hznu c_0227, 9-storey office grid from below, trees at the foot | `block`: four corners, straightened, `xs`/`ys` | 0.78 | | 0.78 |

Straightening from four read corners against hznu's ground-truth homography (c_0174): the annotated window edges lean by a median 5.7° in the photo, 1.55° after `rectify.py`, 1.09° with the dataset's own homography. On the tower, a uniform row step drifted up to 7 px per floor, which is why `xs`/`ys` exist; at 768 px, windows of 20 px make a few pixels of reading error cost half the overlap, so very dense facades need zoomed crops. hznu outlines only the glass: read with the stone surround included (the way CMP annotates, and what the model builds), c_0075 scores 0.58 with every window in the right place.

`tools/rectify.py PHOTO "x,y x,y x,y x,y" OUT` straightens a facade photographed at an angle from its four corners (top-left, top-right, bottom-right, bottom-left), so ordinary street photos can be read like elevations.

Prompt scenarios live in `tools/scenarios/prompts.json` (table, chair, amphora, lamp, bookcase, ring, house, palazzo, spiral stair): each holds the prompt, the spec written for it and the expected size. `python tools/scenarios/run_prompts.py` checks them locally; `run_prompts.rhino(doc)` builds them in Rhino and compares sizes (all nine match).

## License

MIT
