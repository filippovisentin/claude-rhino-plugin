# claude-rhino

A Claude Code plugin that connects Claude to **Rhino 8** (and Grasshopper) through McNeel's official **Rhino-MCP-Platform** router.

**New here? Read the three-page overview, written for designers: [docs/rhino-plugin-overview.pdf](docs/rhino-plugin-overview.pdf)**

It adds:

- **`rhino` MCP server**: a small Node launcher that finds the newest installed `rhino-mcp-router` and runs it over stdio. No version-specific paths in your config, so Rhino package updates don't break it.
- **Viewport images Claude can actually see**: router 0.3.0 returns `get_viewport_image` as one big JSON text block with the image inside it, so Claude gets text instead of a picture, and larger captures exceed the tool-output limit. The launcher unwraps those results into real MCP image content. It only does so when the nested content holds an image, and it rebuilds each item from known fields (`text`, or `image` with an `image/*` type and base64 data), so document text can't turn itself into links or annotations. Every other message passes through unchanged.
- **`build_model` and `check_model` tools**: the launcher adds them to the router's tool list. They take a JSON spec, rewrite the call into McNeel's `run_python` with the spec and paths base64-encoded inside a fixed script (nothing the model writes becomes Python), and trim the reply to one summary line.
- **`rhino-model` skill (text, prompt or image to 3D)**: Claude writes a compact JSON spec (boxes, cylinders, revolves, lofts, pipes, arrays, boolean cuts, and whole buildings with floors, openings and roofs) and the `rhinospec` builder in [`rhino/`](rhino/rhinospec) turns it into solids with one `run_python` call. A spec costs far fewer tokens than RhinoCommon code, cannot run arbitrary code, is strictly validated (known keys only, finite numbers, 2000-part limit), and only ever writes to and clears sublayers of `rhinospec`. For photos of elevations, a `facade` part takes pixel boxes read straight off the image (windows, doors, shop fronts, cornices, mouldings, sills, pillars, balconies, shutters, ornaments) and builds the wall with real openings, frames, glass, glazing bars and projections, plus open porticoes (`arcade`), pediments that rise above the eaves, oculi, round piers, glass or iron railings and spandrel bands, gables, stepped gables and raised parapets (`top`), material zones (`clad`), glazed and garage doors, downpipes; a `palette` gives every family of elements the photo's colours and any element can take its own `color`, each element becomes one solid per layer, and anything that falls outside the facade, or is cut short by its outline, is reported instead of silently dropped. With `style:"classic"` the details follow real architecture (see [docs/architecture.md](docs/architecture.md)): moulded window surrounds with keystones, profiled cornices with dentils, sills with drips, balconies on consoles with balustrades, pilasters, rustication, quoins, shaped ornaments (consoles, cartouches, framed panels), hip and mansard roofs with dormers and chimneys (where the photo shows them), panelled doors with fanlights, louvred shutters, shop signs; `style:"modern"` gives slim dark profiles and glass doors. How faithful the result is, element by element, and what is still missing: [docs/fidelity-gaps.md](docs/fidelity-gaps.md). `column` builds classical columns and colonnades (Tuscan, Doric, Ionic, Corinthian, Vignola's proportions) and `stair` straight or spiral stairs with handrails. A `block` part is a whole rectangular building with one such facade per side, for corner buildings or several photos of one building, with layers per side (Front/Right/Back/Left).
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

- `launch-router.mjs --safe` lists and accepts only modelling and read tools (`SAFE_TOOLS` in `scripts/spec-tool.mjs`): no `run_python`, `run_csharp`, `run_command`, Grasshopper graphs, document open/save/close or slot management. The Rhino panel always uses it, because its replies run without permission prompts.
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
| cmp_b0033, re-read | sills with aprons, full window crowns, full bands (rules fitted on this photo) | 0.78 | 0.79 | 0.84 |
| cmp_b0147 | unseen, sgraffito facade, read blind with the new rules | 0.88 | 0.88 | 0.73 |
| cmp_b0233 | unseen, ornate corner risalit, before the rules / after (fitted) | 0.72 / 0.81 | 0.76 / 0.84 | 0.44 / 0.78 |
| cmp_b0352 | unseen, two buildings, tram wires, read blind with the new rules | 0.63 | 0.63 | 0.54 |
| cmp_b0270 | unseen, read blind / after an overlay self-check (no annotation seen) | 0.76 / 0.78 | 0.76 / 0.76 | 0.53 / 0.57 |

Error-driven loop (`facade_bench.py errors` lists missed and invented objects and the median edge offsets of the matched ones). Round 1, four unseen photos read blind: b0016 0.65, b0061 0.32, b0106 0.21, b0151 0.54 (mean 0.43). The errors repeated across photos (bands read too thin, balconies without their consoles, shutters inside window boxes, closed shutters as windows, flush lintels as cornices, neighbouring buildings ignored) and became rules in the skill. Round 2, three more unseen photos read blind with those rules: b0031 0.74, b0091 0.56, b0136 0.51 (mean 0.60). Different photos, so part of the gap is the photos; the per-class offsets that the rules target did shrink (band bottom edge -35 % to -19 % of its height, balcony bottom -18 % to -10 %). Round 3, three more unseen photos (fire escapes, a commercial front, a palace with 78 shutters): b0046 0.44, b0076 0.48, b0121 0.43 (mean 0.45). Openings stayed good (0.62-0.90); the low classes exposed two round-1 rules drawn from one photo each that did not generalise (decorated friezes are bands, not ornaments; closed shutters have a window under them), now corrected, plus rules that were in the skill but not followed. Lesson: a rule needs agreement on at least two facades before it goes in.

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

### Local facade detector (optional)

A YOLO detector trained on your own machine reads facade elements in a few milliseconds and hands Claude a draft to correct (`detect_facade` tool). It is offered only when a Python with `ultralytics` and trained weights exist (by default `data/venv-det` and the first of `data/det-runs/parts2m`, `parts11s`, `all11s` with `weights/best.pt`, or `RHINO_FACADE_PYTHON` and `RHINO_FACADE_WEIGHTS`). Nothing is downloaded at run time and nothing leaves the machine.

```bash
python -m venv data/venv-det
data/venv-det/Scripts/python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
data/venv-det/Scripts/python -m pip install ultralytics
python tools/facade_yolo.py dataset hznu cfp          # CMP + hznu + CFP -> data/yolo-all
data/venv-det/Scripts/yolo detect train model=yolo11s.pt data=data/yolo-all/cmp.yaml imgsz=1024 epochs=120 patience=30 batch=8 project=data/det-runs name=all11s
python tools/facade_report.py report.md cmp11s all11s  # same test photos for every model
```

The test photos never enter training: the 22 CMP facades Claude read blind, 66 held-out hznu facades and 60 CFP street views. Pixel IoU per element on the 22 CMP facades, and window+door mAP50 on photos of other cities:

| | CMP mean | windows | doors | sills | cornices | hznu (modern) | CFP (street views) |
|---|---|---|---|---|---|---|---|
| Claude reading alone | 0.52 | 0.75 | 0.63 | 0.30 | 0.34 | | |
| detector, CMP only | 0.62 | 0.83 | 0.40 | 0.53 | 0.62 | 0.36 | 0.47 |
| detector, CMP + hznu | 0.62 | 0.84 | 0.56 | 0.49 | 0.58 | 0.67 | 0.59 |
| detector, CMP + hznu + CFP | 0.62 | 0.83 | 0.60 | 0.53 | 0.60 | 0.64 | 0.71 |

The parts model (`python tools/train_data.py parts`, then `train parts --model data/det-runs/yolo11m.pt --batch 4 --run parts2m`, YOLO11m) adds arches, oculi, pediments and finials from MonuMAI and Oxford photos. On unseen photos (`python tools/train_report.py report.md`, 2026-11-06) it scores mAP50 0.764 on CMP, 0.98 on modern facades, 0.83 on Oxford (all11s: 0.32) and 0.985 on monuments, and 0.62 pixel IoU on CMP against Claude's 0.52; it is the default when trained. Inference is about 15 ms per photo against 6 ms for YOLO11s.

When `parts11s` is trained too, `detect_facade` runs both and fuses their boxes (`fuse_boxes` in `tools/facade_yolo.py`: overlapping boxes of a class averaged by confidence, the most confident member's score kept, parts2m counting double). `python tools/ensemble_report.py report.md` scores single models and fusions on the same unseen photos:

| | CMP mAP50 | modern | Oxford | monuments | pixel IoU vs Claude (0.52) |
|---|---|---|---|---|---|
| parts2m | 0.742 | 0.982 | 0.813 | 0.988 | 0.619 |
| parts11s | 0.744 | 0.980 | 0.730 | 0.998 | 0.601 |
| fused, 2:1 (default) | 0.764 | 0.982 | 0.807 | 0.999 | 0.629 |

Plain weighted boxes fusion, which averages scores over every member, reached 0.78 on CMP but moved Oxford between 0.76 and 0.85 with the members' threshold, so it is not the default. A list of weights in `RHINO_FACADE_WEIGHTS` (joined by `;` on Windows, `:` elsewhere) fuses any models, the first counting double.

The scene model (`python tools/train_data.py scene`, then `train scene --run scene2`) outlines buildings, sky, trees, vehicles, people, ground and poles. `tools/silhouette.py` uses its building mask to check a whole model's outline and proportions against the photo (`mask` the photo, `compare` the mesh written by `tools/export_mesh.py` in Rhino; `tools/photo3d.py` solves the camera and real sizes from the building's corners). On 200 photos of the scene test split, scene2's building mask overlaps the human outline at 0.82 IoU against 0.77 for scene11s. As a filter for the facade detector it did not help: on modern glass facades it drops real windows that reflect the sky.

Draft plus Claude's own doors, shops and pillars: 0.63 on CMP. On four modern hznu photos scored through the whole straighten-and-read chain, openings 0.80 for the detector against 0.60 for Claude's readings. Claude still reads shops and pillars better. Licences: CMP is CC BY-SA, hznu CC BY 4.0, [CFP](https://github.com/wbw520/RTFP) states none, so a model trained with CFP is for personal use; train without `cfp` to get one you may share under CC BY-SA.

Prompt scenarios live in `tools/scenarios/prompts.json` (table, chair, amphora, lamp, bookcase, ring, house, palazzo, spiral stair, straight stair, spiral stair with handrail, classic corner palazzo with mansard, villa with hip roof, Doric portico): each holds the prompt, the spec written for it and the expected size. `python tools/scenarios/run_prompts.py` checks them locally; `run_prompts.rhino(doc)` builds them in Rhino and compares sizes (all fourteen match). Default sizes for prompts that give none are in [docs/dimensions.md](docs/dimensions.md).

## License

MIT
