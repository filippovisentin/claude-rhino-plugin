---
name: rhino-model
description: Model 3D geometry in Rhino 8 from a text prompt, a description or a reference image (photo, sketch, plan) - buildings, massing, floor plans, products, furniture, jewellery, mechanical parts. Use when the user asks to model, build, draw, create or rebuild something in Rhino, or says "text to 3D", "image to 3D", "prompt to 3D". Writes a compact JSON spec that the rhinospec builder turns into solids, instead of long RhinoCommon scripts.
---

# Rhino model (spec to 3D)

Write a **JSON spec**, build it with **one** `build_model` call, check **one** small viewport image. A spec is 5-10x cheaper than RhinoCommon code, cannot run arbitrary code, and is rebuilt identically.

## Build call

Call the `rhino` server's **`build_model`** tool with `{"spec": {...}}` (and `check_model` to validate without building). It needs no paths or Python and returns only the summary line.

If those tools are missing (an older plugin session), fall back to `run_python`; the builder lives in `${CLAUDE_PLUGIN_ROOT}/rhino`:

```python
import sys; p=r"${CLAUDE_PLUGIN_ROOT}/rhino"; p in sys.path or sys.path.insert(0,p)
import rhinospec; print(rhinospec.run(r'''<spec json>''', __rhino_doc__))
```

Output is one line: `{"ok":true,"layer":"rhinospec::X","added":12,"removed":0,"bbox":[[..],[..]],"units":"Meters"}` or `{"ok":false,"error":"parts[2].r: must be > 0"}`. Fix exactly the reported path and rebuild.

## Spec

```json
{"units":"m","layer":"Casa","clear":true,"parts":[ ... ]}
```

- `units` `mm|cm|m` (scaled to the document's units). `layer` is a sublayer of `rhinospec` (letters, digits, space `_ . -`, max 64). `clear:true` deletes that sublayer's objects first: **always use it when iterating**, rebuild the whole spec instead of patching objects.
- Every part: `type`, optional `name`, `at:[x,y,z]` (default origin), `rot` (degrees about Z through `at`), `tilt:[about x, about y]` (degrees, applied before `rot`: stand a ring up with `[90,0]`, lay a cylinder down with `[0,90]`), `color:"#rrggbb"`, `cut:[parts]` (boolean difference, world coordinates, no nested cuts), `keep:[parts]` (boolean intersection: only what lies inside every keep part stays; a volume read from two views is an elevation `prism` kept inside the side-profile `prism`), `group:"Name"` (its own sublayer).
- `join:"Name"`: parts sharing it (on the same layer) become one solid. Facades do this by themselves: each shutter, frame, surround or railing is one object, not dozens of pieces.
- **Layers**: everything lands in `rhinospec::<layer>`. Facades and buildings split themselves into named sublayers per object and category (Walls, Windows › Frames/Glass/Bars, Doors, Shopfronts, Cornices, Mouldings, Sills, Pillars, Balconies › Railings/Glass, Shutters, Ornaments, Pediments, Arcades, Spandrels, Floors, Roof), each with its own layer colour. `"lang":"it"` gives Italian names (Muri, Finestre › Telai/Vetri/Traversi, …). For hand-written parts always set `group` (e.g. "Piano", "Gambe") so the user gets one layer per component.

| type | keys | local frame |
|---|---|---|
| box | `size:[x,y,z]` | corner at `at`, spans +x +y +z |
| cyl | `r`,`h` | base centre at `at` |
| cone | `r`,`h`,`r2` (top radius, 0 = point) | base centre |
| sphere | `r` | centre |
| torus | `R`,`r` | centre, in XY |
| extrude | `pts:[[x,y]..]` polygon, `h` | polygon in XY, up +z |
| prism | `pts:[[x,z]..]` profile, `len` | profile in XZ, along +y |
| revolve | `profile:[[r,z]..]` | around the Z axis (vases, knobs, rings, columns) |
| loft | `sections:[{pts,z}..]` rising z | closed polygons, same point count |
| pipe | `path:[[x,y,z]..]`, `r` | path relative to `at` |
| array | `of:part`, `n:[nx,ny,nz]`, `step:[dx,dy,dz]`, `turn` (deg per copy), `pivot:[x,y]` | copies of one part; `turn` makes spirals and radial patterns |
| panel | `size:[w,h]`, `t`, `holes:[[u,v,w,h]..]` | wall in XZ with rectangular holes, thickness +y |
| building | see below | expands to slabs, walls, openings, roof |
| facade | see below | one detailed elevation: wall, openings, mouldings, balconies |
| column | `order: tuscan|doric|ionic|corinthian`, `h`, `d` (default h/7, /8, /9, /10), `count`, `spacing` (3 d), `axis: x|y` | classical column or colonnade standing at `at`: plinth, base, shaft with entasis, capital |
| stair | `kind:"straight"` (`w` 1.0, `tread` 0.28, climbs +y) or `"spiral"` (`r` 0.9, `core` 0.1, `step` 25 deg), `h`, `rail: both|left|right|outer|none` | steps of about 0.17 m from `h`, handrails 0.9 m above the nosings |
| block | see below | a whole rectangular building with a detailed facade on each side |

`building`: `footprint:[[x,y]..]`, `floors`, `floor_h` (3), `wall_t` (0.3), `slab_t` (0.3), `roof:"flat|gable|none"`, `roof_h` (2), `openings:[{wall,offset,width,height,sill,floor:"all"|n,count,gap}]`. Wall `i` runs from footprint point `i` to `i+1`; `offset` is measured from its start along the wall. Gable roofs span the footprint's bounding box.

`facade`: `h` (metres, up to the eaves), `px:[x0,y0,x1,y1]` (the facade's pixel corners in the photo), `els:[{k, box:[x0,y0,x1,y1], grid:[nx,ny,dx,dy] or xs/ys (`xs:[x...]`/`ys:[y...]`: the left/top pixel of each copy of `box`, which keeps its size), bars:[v,h], shape, d, color}]`, optional `t` (0.4), `style`, `palette`, `top:[[x,y]..]` (the wall's outline above the eaves, left to right in the same units as the boxes: one point for a gable peak, the corners of every step for a stepped gable, the raised middle of a parapet; windows in it are kept and cut through, and with `depth` and `roof:"gable"` the ridge runs back from the street, under the steps), `at`, `rot`, `name`, and for a whole building behind it `depth`, `floors`, `roof:"flat|gable|hip|mansard|none"`, `roof_h`, `dormers`, `chimneys` (a count or x positions in photo pixels). Windows read above the eaves of a facade with depth and a pitched roof become dormers at their positions (not with `top`: there they are gable windows); elements that fall outside the facade, or are cut short by its outline, are listed in the result's `notes`. `top` is for facades only, and not with a hip or mansard roof, dormers or chimneys. With `px`, every box is a pixel rectangle of the same photo, `grid` repeats it with pixel steps, and the width follows the photo's proportions. Without `px`, give `w` and boxes as `[u,v,w,h]` metres from the bottom-left (or fractions with `frac:true`). The front face is the XZ plane at `at`; the building lies behind it (+y).

`block`: `w` (along x), `d` (along y), `h`, optional `t` (0.4), `style`, `palette`, `floors`, `roof:"flat|gable|hip|mansard|none"`, `roof_h`, `dormers`, `chimneys` (count or x positions in metres along the front), `at`, `rot`, `name`, and `faces:{front, right, back, left}`, each `{px, els}` (or `{els}` in metres, or `frac:true`) exactly like a facade without `w`/`h`/`t`: the block sets them. Front runs along +x at y=0; right, back and left follow counter-clockwise, each read left to right as seen from outside. Missing faces, or faces with `els:[]`, are plain walls. Layers: `<name> › Front/Right/Back/Left › Windows…` (Italian: Fronte/Destra/Retro/Sinistra), plus Floors and Roof. Use it for corner buildings and for several photos of one building; set `w`/`d` from the photos' proportions.

**Facade and block elements** (`style`, `palette`, every `k` with its default `d`, `deco` shapes, what is built automatically): read `${CLAUDE_SKILL_DIR}/facade-elements.md` before writing any `facade` or `block` part.

The plugin folder, written `<plugin>` in facades.md and photo3d.md, is `${CLAUDE_PLUGIN_ROOT}`.

Limits: 2000 parts after expansion, 1000 facade elements, 500 points per polygon, coordinates within 1e6.

## Workflow

1. **Size first.** Fix real dimensions before writing parts: from the prompt, from a stated reference (door 2.1 m, A4 sheet, coin), or the defaults in `${CLAUDE_PLUGIN_ROOT}/docs/dimensions.md` (furniture, objects, storeys, stairs, roofs). State the assumptions in one line.
2. **Text or prompt to 3D**: decompose into the parts the user would name and give each a `group` in their language. Use `block` for a building described by its facades (counts of floors and windows become `grid`s in metres, `style:"classic"` for historic ones), `building` for free footprints, `stair` for stairs, `revolve` for turned objects, `loft` for tapering forms, `array` for anything repeated, `cut` for holes, slots and openings. Parts that should touch must touch: the floating check catches the rest.
3. **Facade or building from a photo** (steps 3-6: straighten an angled photo, `detect_facade`, the inventory before the spec, the image-to-3D reading rules and the systematic errors measured on unseen photos): read `${CLAUDE_SKILL_DIR}/facades.md` and apply every rule in it before writing the spec; the rules were tuned on benchmarks, none is optional.
7. **Curved and free-form buildings** (towers with a sweeping roof, sails, domes, shells; camera solve with `photo3d`, shape check with `silhouette`): read `${CLAUDE_SKILL_DIR}/photo3d.md`.
8. Build with `clear:true` and trust the one-line summary (counts, bounding box, warnings). `floating` lists parts that touch neither the ground level nor another part: fix those before reporting (a table top above its legs, a balcony off the wall). Call `get_viewport_image` only when the user asks to see the model or a warning can't be understood without it.
9. Report in two or three lines: what was built, the key dimensions, any warnings.

## Token rules

- One `build_model` (or fallback `run_python`) per build; never one call per object.
- Don't call `list_objects` or `get_context` to confirm a build: the summary already gives counts and the bounding box.
- Images are the expensive part: read the input photo once at most 768 px on the long side, and don't take viewport screenshots to check routine builds.
- Use `rhinospec.check(spec)` (same import, no geometry) when unsure the spec is valid and Rhino is busy.
- Fall back to hand-written RhinoCommon (`run_python`) or Grasshopper only for what the spec cannot express (fillets, NURBS surfaces from curves, sweeps along curves). Keep that code short and on the `rhinospec` layer tree.

## Examples

Table, 1.6 x 0.8 m:
```json
{"units":"m","layer":"Tavolo","clear":true,"parts":[
 {"type":"box","name":"piano","at":[0,0,0.72],"size":[1.6,0.8,0.04]},
 {"type":"array","of":{"type":"box","name":"gamba","at":[0.05,0.05,0],"size":[0.05,0.05,0.72]},"n":[2,2,1],"step":[1.45,0.65,0]}]}
```

Two-storey house, 10 x 6 m, windows on the long side:
```json
{"units":"m","layer":"Casa","clear":true,"parts":[{"type":"building","name":"casa","footprint":[[0,0],[10,0],[10,6],[0,6]],
 "floors":2,"floor_h":3,"roof":"gable","roof_h":2.5,
 "openings":[{"wall":0,"offset":1,"width":1.2,"height":1.4,"sill":0.9,"count":3,"gap":1.8},{"wall":2,"offset":4.4,"width":1.2,"height":2.2,"sill":0,"floor":0}]}]}
```

Vase:
```json
{"units":"cm","layer":"Vaso","clear":true,"parts":[{"type":"revolve","profile":[[0,0],[6,0],[9,10],[5,22],[6,25],[0,25]]}]}
```
