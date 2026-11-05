# How facades and buildings are put together

Reference for reading photos and for the `rhinospec` facade planner. Dimensions are typical
values in metres; they are the defaults the planner should fall back on when a photo is too small
to measure a detail.

## 1. The facade as a system

A facade is read in three layers, and every detail belongs to one of them:

1. **Structure and order**: load-bearing wall or frame, floor levels, the bay grid (the vertical
   axes on which openings stack). In masonry the wall gets thinner going up (ground 0.6-0.9 m,
   top 0.4-0.5 m); in frame buildings the facade is a skin hung on slabs and columns.
2. **Tripartition** (base, shaft, crown): almost every pre-1940 urban facade and most later ones.
   - **Base** (ground floor, sometimes mezzanine): taller storey (4-5.5 m), rusticated or clad in
     stone, shop fronts and the main portal, a plinth 0.3-1.0 m high at the foot.
   - **Shaft** (the typical floors): repeated windows on the bay grid, separated by string
     courses at floor or sill level; the *piano nobile* (first floor) is the tallest and richest.
   - **Crown**: main cornice (0.6-1.5 m tall, projecting 0.6-1.2 m), often a frieze below it,
     an attic storey or parapet above it, then the roof.
3. **Ornament**: surrounds, pediments, consoles, keystones, pilasters, balustrades, reliefs. It
   follows the bay grid and floor lines exactly; nothing floats.

The grid is the key to reading: count bays and floors first, then place every element on an axis.

## 2. Storeys and the vertical scale

| Type | Ground | Piano nobile | Typical | Attic | Use |
|---|---|---|---|---|---|
| Historic tenement (1860-1914, Gründerzeit, Haussmann) | 4.0-5.0 | 3.8-4.2 | 3.4-3.8 | 2.8-3.2 | most CMP photos |
| Italian palazzo (Renaissance, Baroque) | 5-7 | 5-6 | 4-5 | 3 | |
| Interwar / modern masonry | 3.2-4.0 | | 3.0-3.2 | | |
| Post-war slab / tower | 3.0-4.5 | | 2.8-3.0 | | hznu towers |
| Office frame | 4.0-5.0 | | 3.4-4.0 | | |

Slabs are 0.2-0.35 m. Window heads usually sit 0.3-0.6 m below the next floor line, sills
0.8-1.0 m above the floor (lower, 0.2-0.5 m, for French windows and balconies).

## 3. Openings

**Proportions.** Historic windows are vertical, height about 2 x width (1.0-1.3 wide, 2.0-2.6
high on main floors; attic windows are squarer). Modern windows are freer; ribbon windows run
horizontally. Doors 1.0-1.2 single, 1.6-2.4 double leaf, 2.4-3.5 high; a portal with fanlight
reaches 4-5 m.

**Anatomy of a historic window**, outside in:

- **Surround / architrave** (*cornice di finestra*): a moulded band 0.12-0.25 wide around the
  opening, projecting 0.03-0.08 from the wall. Often "eared" (widened at the top corners).
- **Head**: plain lintel, or a crowning element above the surround: **frieze** + **cornice**
  (flat hood), **triangular pediment**, **segmental pediment**, broken pediment. Pediments
  overhang the surround by 0.05-0.15 each side, project 0.15-0.30, and are 0.25-0.6 high.
  Brackets (**consoles**, *mensole*) often carry the hood at both ends.
- **Keystone** (*chiave di volta*) at the crown of arches and sometimes on flat lintels:
  0.15-0.3 wide, slightly taller than the surround, projecting a little more.
- **Sill** (*davanzale*): a stone slab 0.05-0.10 thick projecting 0.05-0.10, wider than the
  opening by the surround width; below it an **apron** panel and sometimes small consoles.
- **Reveal** (*mazzetta*): the wall depth between face and frame; frames sit 0.10-0.25 behind
  the face in masonry, almost flush in modern skins.
- **Frame and sashes**: frame 0.05-0.08; casements split into two leaves (one vertical bar) and
  a transom near the top (one horizontal bar at 70-80 % of the height); older windows have more
  glazing bars.
- **Shutters / blinds**: hinged leaves beside the opening, each half the opening width.

**Arches.** Semicircular (rise = half span) on Renaissance and Neo-Renaissance piano nobile;
segmental (rise 1/6-1/4 span) on simpler floors; the arch has its own archivolt (moulded band)
following the curve and a keystone.

## 4. Horizontal elements

Profiles are what make them read as architecture: a flat box looks like a shelf.

| Element | Height | Projection | Profile (bottom to top) |
|---|---|---|---|
| Plinth / base course | 0.3-1.0 | 0.03-0.10 | plain block, chamfered or torus on top |
| String course (*marcapiano*) | 0.15-0.4 | 0.05-0.15 | fillet, cyma, fillet |
| Sill course | 0.1-0.2 | 0.05-0.1 | slab with drip |
| Main cornice (*cornicione*) | 0.6-1.5 | 0.6-1.2 | bed moulding (cyma reversa), dentils or modillions, corona (vertical face), cyma recta, fillet |
| Frieze | 0.4-1.0 | 0 (flush) | flat band, sometimes with reliefs or windows of the attic |
| Parapet / attic | 0.8-1.2 | 0 | solid wall or balustrade over the cornice |

A classical cornice always projects about as much as it is tall, and grows outward toward the
top in 3-5 steps; the topmost step is the **corona**, a vertical face that throws the shadow line.
**Dentils** are small blocks (about 0.1 wide, 0.15 high, 0.1 apart) under the corona;
**modillions** are larger scrolled brackets (0.15-0.25 wide, every 0.5-0.8 m).

## 5. Vertical elements

- **Pilasters** (*lesene*): flat columns 0.4-0.8 wide, 0.05-0.15 proud, with a base (0.2-0.4)
  and a capital (0.3-0.6) that is wider than the shaft. They mark bays or corners, often spanning
  two floors (giant order).
- **Quoins** (*cantonali*): alternating long and short stone blocks at the building corners.
- **Columns** at portals and loggias; half columns on richer facades.
- **Risalit** (*avancorpo*): a slightly projecting section (0.1-0.6) of the whole facade,
  usually the centre or the ends, with its own crowning (gable, attic, dome).

## 6. Wall surface

- **Rustication** (*bugnato*): ground floor or the whole base split into courses by grooves
  0.02-0.05 deep, course height 0.3-0.6; sometimes vertical joints too. Rustication also
  radiates around arches (voussoirs).
- Render (smooth or textured), exposed brick, stone ashlar, cladding panels (modern: a grid of
  joints, 1.2-1.5 m modules).

## 7. Balconies, loggias, bay windows

- **Balcony** on stone slab 0.12-0.2 thick, projecting 0.6-1.5, carried by 2-4 **consoles**
  (0.2-0.3 wide, as deep as the slab, tapering down 0.4-0.8). Railing 0.9-1.1 high: either a
  **balustrade** (plinth 0.15, balusters 0.12-0.15 diameter every 0.2-0.3, handrail 0.12-0.2)
  or wrought iron (thin bars every 0.10-0.12, handrail).
- Long balconies on the piano nobile run across several bays; small ones sit in front of one
  French window.
- **Loggia**: recessed balcony, the facade plane continues at its front.
- **Bay window / oriel** (*bovindo*): a projecting box 0.6-1.2 deep over one or more storeys.

## 8. Roofs

| Type | Where | Geometry |
|---|---|---|
| Flat with parapet | modern, many palazzi | slab, parapet 0.8-1.2 |
| Gable (*a capanna*) | houses, row ends | two planes, 30-45 deg |
| Hip (*a padiglione*) | Italian palazzi, villas | four planes, 25-35 deg |
| Mansard | Paris, Central Europe tenements | steep lower slope (60-75 deg, with dormers) + flat upper slope |
| Tiled pitched behind a cornice | most European tenements | ridge parallel to the street |

**Dormers** (*abbaini*) stand on the roof slope on the window axes below, 1.0-1.5 wide.
Eaves overhang 0.3-1.0 on houses; on tenements the main cornice is the eave.

## 8b. From the anatomy to spec elements

| element in the photo | spec |
|---|---|
| window, French window, shop front, door | `window`, `door`, `shop` (shape rect, arch, seg; `round` for an oculus) |
| open portico, loggia, pilotis floor | `arcade` with `d` = recess depth; doors inside go on its back wall |
| temple front over a risalit or portal | `pediment` (rises above the eaves; its oculus and reliefs are kept) |
| window crown | `cornice` (shape flat, tri, seg) |
| string course, main cornice, slab edge, eave | `molding` (`d` 0.6-1.2 for a main cornice) |
| pilaster, lesene, pier | `pillar`; `shape:"round"` for round piers and engaged columns |
| giant order spanning floors | a `column` part in front of the facade |
| balcony | `balcony` with `rail` balustrade, iron, solid or glass |
| risalit, bay, setback | a second facade part moved forward or back with `at` |
| dormer, chimney | windows read above the eaves of a facade with depth and a pitched roof; `chimneys:[x...]` |
| rusticated base, quoins | `rustic`, `quoin` |
| dark band between ribbon windows | `spandrel` |
| gable end, stepped gable, raised parapet | `top` outline of the facade (with `depth` and a gable roof: ridge running back) |
| stone base, timber or brick zone on the wall | `clad` (`palette.clad` or the element's `color`) |
| glazed or patio door, garage door | `door` with `leaf:"glass"` or `leaf:"garage"` |
| downpipe, gutter | `pipe` |
| finial, urn, ball or pinnacle on a parapet | `finial` with `shape` urn, ball or spire |
| colours of wall, stone trim, frames, shutters, roof | `palette` |

## 9. Reading rules that follow from the above

1. Count bays and floors first; every element sits on a bay axis or a floor line.
2. The photo's outline stops at the building line (party walls, sky, pavement).
3. Set the scale from storeys (table in section 2) or a door (2.1-2.4 high).
4. Window boxes include the surround; record pediments, sills and keystones separately.
5. Ornament is symmetric about the bay axis and repeats on every bay of the same floor.
6. Things that look like boxes in the photo are almost always profiles: cornices, string courses,
   sills and pediments should be built with profiles, not blocks.
7. A balcony is slab + consoles + railing; never a floating box.
