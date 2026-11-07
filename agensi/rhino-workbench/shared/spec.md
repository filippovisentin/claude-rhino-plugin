# Rhinospec schema

## Keys depend on the part type

The common primitive keys below do not apply to every macro. The runtime rejects unknown keys. Use this table before copying attributes across types:

| Type | Shared keys accepted in addition to that type's own fields |
|---|---|
| Primitive geometry | `type`, `name`, `at`, `rot`, `tilt`, `color`, `cut`, `keep`, `group`, `join` |
| `array` | `type`, `name`, `group`; placement is in `of`, not `at` on the array |
| `building` | `type`, `name`, `at`, `color`; no `rot` |
| `facade`, `block`, `stair` | `type`, `name`, `at`, `rot`, `color` |
| `column` | `type`, `name`, `at`, `rot`; no `color` |

Do not add `group`, `tilt`, `cut`, `keep` or `join` to the composite macros `building`, `facade`, `block`, `column` and `stair`; `array` does take `group`. Use the macro's `name`; it creates the appropriate sublayers. Top-level `lang:"it"` selects Italian generated layer names. Rotate/place primitive parts or use the macro's supported fields when an unsupported transform is needed; do not invent a common key.

Input syntax of the claude-rhino-plugin runtime (see runtime.md). If the builder rejects a key this file allows, the runtime is older: say so and drop the key.


```json
{"units":"m","layer":"Casa","clear":true,"parts":[ ... ]}
```

- `units` `mm|cm|m` (scaled to the document's units). `layer` is a sublayer of `rhinospec` (letters, digits, space `_ . -`, max 64). `clear:true` deletes that sublayer's objects first: **always use it when iterating**, rebuild the whole spec instead of patching objects.
- Primitive parts: `type`, optional `name`, `at:[x,y,z]` (default origin), `rot` (degrees about Z through `at`), `tilt:[about x, about y]` (degrees, applied before `rot`: stand a ring up with `[90,0]`, lay a cylinder down with `[0,90]`), `color:"#rrggbb"`, `cut:[parts]` (boolean difference, world coordinates, no nested cuts), `keep:[parts]` (boolean intersection: only what lies inside every keep part stays; a volume read from two views is an elevation `prism` kept inside the side-profile `prism`), `group:"Name"` (its own sublayer). Composite macros follow the per-type table above.
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

`style`: `"classic"` for pre-1940 ornate facades (tenements, palazzi, Gründerzeit, Haussmann). It puts a moulded surround (`sur`, default 0.15 m) around every window and door box, which stays the opening as read (glass and frame), with a keystone on arches and oculi; profiles cornices and string courses (a main cornice with `d` ≥ 0.3 and height ≥ 0.4 gets bed moulding, dentils and corona); profiles sills; adds a base cornice to pediments; puts balconies on consoles with a stone balustrade; gives `pillar` a base and capital. `"modern"`: slim dark profiles, dark glass, glass doors. `"plain"` (default) keeps flat detailing. Balconies take `rail: balustrade|iron|solid|glass`. `palette:{wall, trim, frames, glass, shutters, doors, railings, roof, spandrels, clad}` (`#rrggbb`) gives each family the photo's colour (glass parapets take `railings`); `detect_facade` proposes one. Any element takes its own `color` when it differs from its family (a stone plinth under brick, dark shop fronts under white sashes, a yellow garage door): it wins over style and palette, and glass stays glass. Anatomy and typical sizes: [architectural anatomy](architecture.md).

| k | becomes | default `d` |
|---|---|---|
| window, door, shop | hole in the wall, frame, glass, `bars:[vertical, horizontal]` glazing bars; `shape` rect, arch, seg, and round for windows (oculi). Doors take `leaf`: `panel` (panelled wood, default), `glass` (French or patio door, default in `modern`), `garage` (sectional door) | recess 0.12 / 0.15 / 0.10 |
| arcade | open portico or loggia arch (rect, arch, seg): no glazing; a back wall at depth `d`, a ceiling and side returns per row; doors and windows read inside an arch go on its back wall | 3.0 |
| pediment | temple front over a risalit or portal: raking cornices, set-back tympanum and base; rises above the eaves, and an oculus or relief inside it is kept | 0.5 |
| cornice | hood or pediment above one window | projects 0.30 |
| molding | long horizontal band: entablature under the roof, string course between floors | 0.06 (use 0.4-0.8 for a main cornice) |
| sill | sill with its apron under one window, as wide as the window surround | 0.06 |
| pillar | pier or pilaster; `shape:"round"` a cylindrical pier or engaged/free column (`d` = how far it stands out, the diameter by default) | 0.12 |
| balcony | slab 0.15 m plus railing, box = underside of the slab to railing top (`classic` adds the consoles under it) | 1.0 |
| blind | shutter beside a window | 0.04 |
| deco | consoles, cartouches, reliefs, pilaster capitals | 0.04 |
| rustic | rusticated base: stone courses 0.45 m high with grooves, interrupted by the openings | 0.03 |
| quoin | corner stones: one box per corner strip, courses alternating full and 60 % width | 0.04 |
| spandrel | dark panel between ribbon windows (modern facades) | 0.03 |
| clad | a zone of another material on the wall (stone base under brick, timber ground floor, brick band): a flat layer with the openings cut through; colour from `palette.clad` or `color` | 0.03 |
| pipe | downpipe (a gutter when wider than tall) on brackets, standing off the wall by `d` | 0.04 |
| finial | finial or urn on a parapet, gable or cornice: box = pedestal foot to tip; `shape` `urn` (default), `ball` or `spire`; on the wall's top edge it rises above the eaves, one floating above the wall is dropped and noted | - |

`deco` takes `shape`: `console` (bracket under a sill, hood or cornice: deep at the top, tapering down; read each bracket as one box, `xs` for pairs), `oval` (cartouche, medallion), `panel` (framed sunk panel, e.g. under windows), `block` (default). Built automatically from the boxes you read: doors wider than 1.3 m get two panelled leaves, taller than 2.7 m (or arched) a glazed fanlight; shop fronts taller than 2.4 m keep their top fifth as a sign fascia; `blind` shutters get louvres (one profile per shutter); in `classic`, arched surrounds follow the arch and triangular pediments get raking cornices over a recessed tympanum. A `block` takes `chimneys` (stacks on the ridge). A `block` with a gable, hip or mansard roof takes `dormers`: how many stand on each long slope (front and back), on the window axes when the count matches the bays.

Limits: 2000 parts after expansion, 1000 facade elements, 500 points per polygon, coordinates within 1e6.
