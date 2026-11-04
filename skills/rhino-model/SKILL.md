---
name: rhino-model
description: Model 3D geometry in Rhino 8 from a text prompt, a description or a reference image (photo, sketch, plan) - buildings, massing, floor plans, products, furniture, jewellery, mechanical parts. Use when the user asks to model, build, draw, create or rebuild something in Rhino, or says "text to 3D", "image to 3D", "prompt to 3D". Writes a compact JSON spec that the rhinospec builder turns into solids, instead of long RhinoCommon scripts.
---

# Rhino model (spec to 3D)

Write a **JSON spec**, build it with **one** `run_python` call, check **one** small viewport image. A spec is 5-10x cheaper than RhinoCommon code, cannot run arbitrary code, and is rebuilt identically.

## Build call

Call the `rhino` server's **`build_model`** tool with `{"spec": {...}}` (and `check_model` to validate without building). It needs no paths or Python and returns only the summary line.

If those tools are missing (an older plugin session), fall back to `run_python`; the builder lives in `../../rhino` relative to this skill's base directory:

```python
import sys; p=r"<plugin>\rhino"; p in sys.path or sys.path.insert(0,p)
import rhinospec; print(rhinospec.run(r'''<spec json>''', __rhino_doc__))
```

Output is one line: `{"ok":true,"layer":"rhinospec::X","added":12,"removed":0,"bbox":[[..],[..]],"units":"Meters"}` or `{"ok":false,"error":"parts[2].r: must be > 0"}`. Fix exactly the reported path and rebuild.

## Spec

```json
{"units":"m","layer":"Casa","clear":true,"parts":[ ... ]}
```

- `units` `mm|cm|m` (scaled to the document's units). `layer` is a sublayer of `rhinospec` (letters, digits, space `_ . -`, max 64). `clear:true` deletes that sublayer's objects first: **always use it when iterating**, rebuild the whole spec instead of patching objects.
- Every part: `type`, optional `name`, `at:[x,y,z]` (default origin), `rot` (degrees about Z through `at`), `tilt:[about x, about y]` (degrees, applied before `rot`: stand a ring up with `[90,0]`, lay a cylinder down with `[0,90]`), `color:"#rrggbb"`, `cut:[parts]` (boolean difference, world coordinates, no nested cuts), `group:"Name"` (its own sublayer).
- **Layers**: everything lands in `rhinospec::<layer>`. Facades and buildings split themselves into named sublayers per object and category (Walls, Windows › Frames/Glass/Bars, Doors, Shopfronts, Cornices, Mouldings, Sills, Pillars, Balconies, Shutters, Ornaments, Floors, Roof), each with its own layer colour. `"lang":"it"` gives Italian names (Muri, Finestre › Telai/Vetri/Traversi, …). For hand-written parts always set `group` (e.g. "Piano", "Gambe") so the user gets one layer per component.

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

`facade`: `h` (metres), `px:[x0,y0,x1,y1]` (the facade's pixel corners in the photo), `els:[{k, box:[x0,y0,x1,y1], grid:[nx,ny,dx,dy], bars:[v,h], d}]`, optional `t` (0.4), `at`, `rot`, `name`. With `px`, every box is a pixel rectangle of the same photo, `grid` repeats it with pixel steps, and the width follows the photo's proportions. Without `px`, give `w` and boxes as `[u,v,w,h]` metres from the bottom-left (or fractions with `frac:true`). The front face is the XZ plane at `at`; the building lies behind it (+y).

`block`: `w` (along x), `d` (along y), `h`, optional `t` (0.4), `floors`, `roof:"flat|gable|none"`, `roof_h`, `at`, `rot`, `name`, and `faces:{front, right, back, left}`, each `{px, els}` (or `{els}` in metres, or `frac:true`) exactly like a facade without `w`/`h`/`t`: the block sets them. Front runs along +x at y=0; right, back and left follow counter-clockwise, each read left to right as seen from outside. Missing faces are plain walls. Layers: `<name> › Front/Right/Back/Left › Windows…` (Italian: Fronte/Destra/Retro/Sinistra), plus Floors and Roof. Use it for corner buildings and for several photos of one building; set `w`/`d` from the photos' proportions.

`style`: `"classic"` for pre-1940 ornate facades (tenements, palazzi, Gründerzeit, Haussmann). It turns every window and door box into a moulded surround (`sur`, default 0.15 m) around a smaller opening, with a keystone on arches; profiles cornices and string courses (a main cornice with `d` ≥ 0.3 and height ≥ 0.4 gets bed moulding, dentils and corona); profiles sills; adds a base cornice to pediments; puts balconies on consoles with a stone balustrade; gives `pillar` a base and capital. `"plain"` (default) keeps flat modern detailing. Balconies take `rail: balustrade|iron|solid`. Anatomy and typical sizes: `docs/architecture.md`.

| k | becomes | default `d` |
|---|---|---|
| window, door, shop | hole in the wall, frame, glass (door: wooden leaf), `bars:[vertical, horizontal]` glazing bars | recess 0.12 / 0.15 / 0.10 |
| cornice | hood or pediment above one window | projects 0.30 |
| molding | long horizontal band: entablature under the roof, string course between floors | 0.06 (use 0.4-0.8 for a main cornice) |
| sill | sill with its apron under one window, as wide as the window surround | 0.06 |
| pillar | free-standing column or pier, e.g. the jambs of a portal | 0.12 |
| balcony | slab 0.15 m plus railing, box = slab to railing top | 1.0 |
| blind | shutter beside a window | 0.04 |
| deco | consoles, cartouches, reliefs, pilaster capitals | 0.04 |
| rustic | rusticated base: stone courses 0.45 m high with grooves, interrupted by the openings | 0.03 |
| quoin | corner stones: one box per corner strip, courses alternating full and 60 % width | 0.04 |

`deco` takes `shape`: `console` (bracket under a sill, hood or cornice: deep at the top, tapering down; read each bracket as one box, `xs` for pairs), `oval` (cartouche, medallion), `panel` (framed sunk panel, e.g. under windows), `block` (default). Built automatically from the boxes you read: doors wider than 1.3 m get two panelled leaves, taller than 2.7 m (or arched) a glazed fanlight; shop fronts taller than 2.4 m keep their top fifth as a sign fascia; `blind` shutters get louvre slats; in `classic`, arched surrounds follow the arch and triangular pediments get raking cornices over a recessed tympanum. A `block` takes `chimneys` (stacks on the ridge). A `block` with a gable, hip or mansard roof takes `dormers`: how many stand on each long slope (front and back), on the window axes when the count matches the bays.

Limits: 2000 parts after expansion, 1000 facade elements, 500 points per polygon, coordinates within 1e6.

## Workflow

1. **Size first.** Fix real dimensions before writing parts: from the prompt, from a stated reference (door 2.1 m, A4 sheet, coin), or the defaults in `docs/dimensions.md` (furniture, objects, storeys, stairs, roofs). State the assumptions in one line.
2. **Text or prompt to 3D**: decompose into the parts the user would name and give each a `group` in their language. Use `block` for a building described by its facades (counts of floors and windows become `grid`s in metres, `style:"classic"` for historic ones), `building` for free footprints, `stair` for stairs, `revolve` for turned objects, `loft` for tapering forms, `array` for anything repeated, `cut` for holes, slots and openings. Parts that should touch must touch: the floating check catches the rest.
3. **Photo taken at an angle** (facade a trapezoid, verticals converging): read only the four facade corners, then straighten it and read the result instead:
   `python "<plugin>/tools/rectify.py" PHOTO "x,y x,y x,y x,y" OUT.jpg [--ratio W/H]` with corners top-left, top-right, bottom-right, bottom-left (needs Python with numpy and Pillow). Pass `--ratio` when the real proportions are known (bay count x bay width over floor count x floor height); otherwise they are estimated from the corners (a few % off). Read OUT with `px:[0,0,OUT width,OUT height]`. Measured on a warped CMP photo: no accuracy lost against reading the frontal photo.
4. **Facade photo with `detect_facade` listed** (a local detector trained on facade datasets): call it on the image you will read (the straightened one from step 3, or the photo itself), then correct its draft instead of reading every element. Keep its windows, sills, cornices, mouldings, balconies, blinds and deco; check doors, shops and pillars yourself (its weak classes); set `px` to the facade's own corners and `h`; merge overlapping duplicates (stacked mouldings, pillar fragments into one shaft), drop boxes on neighbouring buildings and tiny false shops, but keep dormers and pediment ornaments of this building (dropping them cost 0.06 on cmp_b0121); add `rustic`/`quoin`. Measured on 22 unseen CMP facades: draft 0.62 IoU per element, draft plus Claude's doors/shops/pillars 0.63, Claude alone 0.52; on modern Hangzhou facades openings 0.80 against 0.60. The rules below still apply to what you correct.
5. **Inventory before the spec, check after the build.** The model must hold the same elements as the photo; a missing pediment makes the reading useless whatever the window accuracy. Before writing the spec, list in one compact line per group what the photo shows: volumes (wings, risalit, setbacks, lower bodies), roof (type, dormers and where, chimneys, parapet, finials), crown (main cornice, attic, pediments, gables), vertical order (lesenes, pilasters, columns, quoins), each floor (opening count, shape rect/arch/seg/round, hoods tri/seg/flat, sills, panels, balconies and railing type), ground floor (portico or arcade, shops and signs, doors, plinth, basement vents, steps), materials and colours. Map every item to a spec element; when none fits, say so in one line rather than dropping it silently. Never add what the photo does not show (a roof hidden behind a cornice stays flat, no invented dormers). After building, compare the model with the photo item by item (`notes` in the result lists elements that fell outside the facade) and fix what is missing.
   - A pediment over a risalit is `k:"pediment"` with its full box, rising above the eaves; an oculus or a relief inside it is kept. A cornice-height `molding` is not a pediment.
   - `palette` takes the photo's colours (wall, trim, frames, glass, shutters, doors, railings, roof); `detect_facade` proposes one from the image.
   - A risalit or bay that stands forward is a second facade part over its width with `at` moved a few tens of cm towards the street.
   - An open portico, loggia or pilotis floor is `k:"arcade"` (shape arch/rect/seg, `d` = how deep the recess is): one box per arch; doors and windows read inside an arch are built on its back wall. Do not read an open arch as a shop window.
   - Oculi and round windows: `shape:"round"`. Round piers and free or engaged columns on a facade: `k:"pillar", shape:"round"` (`d` = how far it stands out; the diameter for a free column); a classical order spanning floors can also be a `column` part placed in front.
   - Railings: `rail:"iron"` for wrought iron, `"glass"` for glass or frosted panels between posts, `"solid"` for a masonry or concrete parapet, `"balustrade"` for stone balusters.
   - Modern buildings: `style:"modern"` (slim dark profiles, glass doors), `k:"spandrel"` for the dark panels between ribbon windows, plain `molding` for slab edges and eaves.
   - Dormers: keep the dormer windows read above the eaves on a facade with `depth` and a pitched roof: they become dormers at those positions. Chimneys: `chimneys:[x, ...]` in photo pixels where the stacks stand.
6. **Image to 3D**: read the image once and don't describe it back. For a frontal elevation use `facade` with `px`: read pixel corners straight off the photo, one element per box, `grid` for every regular row or column of identical elements (it is the biggest token saver). Set `h` from floor count (about 3 m per modern floor, 4-4.5 m per historic one) or a known size (door 2.1-2.4 m). Read the outline first (`px` = this building only: stop at neighbours, sky and pavement), then openings row by row, then the mouldings, sills and hoods that frame them. Rules that measurably raise accuracy:
   - One box per separately framed sash: a triple window with solid piers between the panes is three windows, not one wide one.
   - Tall or uneven facades: give the real start of every column and row with `xs:[...]` / `ys:[...]` (pixels, same as `box`) instead of one `grid` step. A uniform step drifts several pixels per floor and costs a quarter of the overlap on small windows (measured on a 13-storey tower).
   - Facades are regular: if a column of windows repeats on every floor, a pane hidden by a tree, shadow or sign is still there; add it at the column's position.
   - Read thin elements at their full architectural extent (measured on CMP: this alone took two facades from 0.51 and 0.44 to 0.84 and 0.78 mean IoU):
     - a **sill** box runs from the slab top down to the bottom of the apron or panel under it (often 0.2-0.4 of the window height) and is wider than the window by about a quarter of the window width on each side;
     - a **cornice** over a window covers the whole crown, from the window top (consoles and frieze included) to the top of the hood, and is as wide as the sill;
     - a **molding** covers the whole band, every bead line included; the main cornice runs from the eaves down to below its brackets and frieze (often 1.5-2.5 times a string course); a projecting eave with a soffit band under a pitched roof is a molding too, a bare roof edge is not;
     - a balustrade panel under a window is a `balcony` (with `rail:"balustrade"`) even when it barely projects; a lowered roller blind is a `blind`;
     - ground-floor openings that reach the pavement are `door`s, or `shop`s when they carry a sign, a shop window or a grille: a shop box runs from the pavement to the top of its sign. Read their columns on their own, they often don't line up with the windows above.
   - Systematic errors measured on unseen photos (`tools/facade_bench.py errors`), and their fixes:
     - bands come out too thin: the bottom edge of a molding was 20-50 % of its height too high on every photo. Put the bottom edge at the lowest bead, dentil or shadow line of the band;
     - a balcony box runs from the railing top down to the bottom of its consoles or slab shadow (read it about 20 % taller than the slab and railing alone); a door box runs to the threshold;
     - a window box is the glass plus its own frame; open shutters beside it are separate `blind` boxes, never part of the window; a closed shutter covering a window gets both boxes, the `window` and the `blind` over it (one facade suggested blind only; a second one, with 78 shutters, showed both);
     - an arch's archivolt or a flat lintel flush with the wall is not a `cornice`: only a projecting hood or pediment is;
     - a continuous horizontal band is a `molding` even when it is decorated (meander, chequer, reliefs: confirmed on two facades after one suggested otherwise); `deco` is for discrete ornaments, listed one by one (a grid when they repeat); read a band at every floor line where the photo shows one;
     - flat pilaster strips between windows, with or without capitals, are `pillar`s, not `deco`;
     - ground-floor arcades and large arched openings on a street front are `shop`s, not windows; a bay window is read sash by sash, like any other window;
     - small balustrade panels under single windows are `balcony`s even when they barely project (missed again when read as `deco`); hoods over dormers are `cornice`s;
     - small ornaments are the most missed class (18 of 20 on one facade): after the openings, sweep the facade once only for consoles, keystone heads, reliefs, cartouches and panels, and list each;
     - neighbouring buildings in the frame are facades too: read them as well (their own `facade` parts, or the same px frame), the user can drop them later.
   - After reading, draw the boxes over the photo (`python tools/facade_bench.py overlay ID PRED` for CMP) and fix what is visibly off before building; on an unseen facade this raised the mean from 0.53 to 0.57 (a missed shop).
   - Thin elements are a few pixels tall: when the photo is small, read them on a zoomed crop (`python tools/facade_bench.py crop ID x0 y0 x1 y1` for CMP; any crop works the same way: px = crop origin + crop pixel / scale).
   - Windows usually include their surround/frame in the box; glazing bars go in `bars`, not as separate windows. An opaque vent panel or spandrel inside the same frame is part of the window (one box, not a `blind`); a continuous recessed glass strip is one wide window with `bars`.
   - Brackets and consoles under a cornice, keystones, garlands and capitals are `deco`: list them (a grid of brackets is one element).
   - Signs, awnings and shop windows on the ground floor are one `shop` box per storefront, sign included.
   - Two or more sides visible (corner building, angled wings): one `block`, each visible side straightened and read as its own face; a side that isn't visible stays a plain wall.
   - Historic facade: set `style:"classic"`, read the main cornice as one `molding` with `d` 0.6-1.2, the string courses between floors as thin `molding`s, the ground floor as `rustic` when it shows horizontal joints, and choose the roof the photo shows (`mansard` for steep tiled roofs with dormer windows, `hip` for four slopes).
   - Before building, check the spec once against the photo: each floor should have the same column count unless the photo clearly breaks the rhythm. For perspective photos or plans, use `building` and primitives from the main proportions.
5. Build with `clear:true` and trust the one-line summary (counts, bounding box, warnings). `floating` lists parts that touch neither the ground level nor another part: fix those before reporting (a table top above its legs, a balcony off the wall). Call `get_viewport_image` only when the user asks to see the model or a warning can't be understood without it.
6. Report in two or three lines: what was built, the key dimensions, any warnings.

## Token rules

- One `run_python` per build; never one call per object.
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
