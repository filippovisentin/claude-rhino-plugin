# Facade and block elements

Reference for the `k` of every `facade` or `block` element; the spec keys are in SKILL.md.

`style`: `"classic"` for pre-1940 ornate facades (tenements, palazzi, Gründerzeit, Haussmann). It puts a moulded surround (`sur`, default 0.15 m) around every window and door box, which stays the opening as read (glass and frame), with a keystone on arches and oculi; profiles cornices and string courses (a main cornice with `d` ≥ 0.3 and height ≥ 0.4 gets bed moulding, dentils and corona); profiles sills; adds a base cornice to pediments; puts balconies on consoles with a stone balustrade; gives `pillar` a base and capital. `"modern"`: slim dark profiles, dark glass, glass doors. `"plain"` (default) keeps flat detailing. Balconies take `rail: balustrade|iron|solid|glass`. `palette:{wall, trim, frames, glass, shutters, doors, railings, roof, spandrels, clad}` (`#rrggbb`) gives each family the photo's colour (glass parapets take `railings`); `detect_facade` proposes one. Any element takes its own `color` when it differs from its family (a stone plinth under brick, dark shop fronts under white sashes, a yellow garage door): it wins over style and palette, and glass stays glass. Anatomy and typical sizes: `${CLAUDE_PLUGIN_ROOT}/docs/architecture.md`.

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
