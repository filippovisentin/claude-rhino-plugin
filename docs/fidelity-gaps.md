# Image-to-3D fidelity: what the model misses

Five photos read to 3D the full way (inventory of what the photo shows, detector draft, Claude's
corrections, build, side-by-side render), to list what is missing rather than score box overlap.
The rule: the model must hold the same architectural elements as the photo; a missing pediment
makes the reading useless however good the window IoU.

| photo | type |
|---|---|
| cmp_b0121 | classical palazzo: central risalit, pediment with relief and oculus, giant ionic columns, hip roof with dormers |
| cmp_b0186 | ornate Prague tenement: arched windows, cartouche hoods, pediments, two balconies, rustication, shops |
| hznu d_0140 | modern office slab: ribbon windows over dark spandrels, pilotis arcade with canopy, lower wing |
| cfp_0003 | colonial stone palace, steep street perspective: open five-arch portico, two continuous iron balconies, oculi, finials |
| cfp_0196 | Japanese apartment block: continuous balconies with frosted glass parapets, round tiled piers, timber ground floor, thin eave |

## Gaps, by cause and priority

| # | gap | seen in | cause | priority |
|---|---|---|---|---|
| 1 | classic windows come out about half size: the surround is carved inside the read box | b0186, cfp_0003, b0121 | builder | P1 |
| 2 | anything above the eaves line (pediment, gable, attic, dormer windows) is clipped without a warning | b0121 | builder | P1 |
| 3 | colours are fixed (cream wall, white frames, light glass, green shutters) instead of the photo's | all five | builder + detector | P1 |
| 4 | elements visible in the photo left out of the spec (pediment, stairs, quoins, lesenes, arch and hood shapes, rustication, basement vents, the second building) | all five | reading | P1: inventory checklist before and after |
| 5 | elements not in the photo added (a mansard with dormers on a facade whose roof is not visible) | b0186 | reading | P1: no invention rule |
| 6 | open portico / loggia / pilotis: arches become glazed shop windows, no recessed back wall | cfp_0003, d_0140 | builder | P2 |
| 7 | railings: iron bars too dense (read as a black wall); no glass or panel parapet | cfp_0003, cfp_0196 | builder | P2 |
| 8 | one plane per facade: risalit, bays and setbacks are flat | b0121, d_0140 | builder + reading (a second facade part offset in y works today) | P2 |
| 9 | round piers and engaged columns are flat pilasters | b0121, cfp_0003, cfp_0196 | builder | P2 |
| 10 | modern style still uses classical mouldings and panelled doors; no spandrel bands | d_0140, cfp_0196 | builder | P2 (style `modern` and `spandrel` started) |
| 11 | round and oval windows (oculi) | b0121, cfp_0003 | builder | P2 |
| 12 | dormers and chimneys evenly spaced, not where the photo has them | b0121 | builder | P2 |
| 13 | detector classes: no portico, pediment, modern balcony, spandrel, oculus | all | detector training data | P3 |
| 14 | finials and urns on parapets | cfp_0003 | builder | P3 |
| 15 | checking renders have no shadows, so relief in the wall colour disappears | b0186 | verification tooling | P2 |

## Fixed (P1)

- 1: the read box is the opening; the classic surround is built around it (narrowed at the facade edge).
- 2: `k:"pediment"` rises above the eaves (raking cornices, set-back tympanum, base); an oculus or a
  relief inside it is kept and brought in front of the tympanum. Elements that fall outside a facade
  are reported in the result's `notes` instead of vanishing.
- 3: `palette` on facades and blocks colours each family (wall, trim, frames, glass, shutters, doors,
  railings, roof, spandrels); `detect_facade` proposes one sampled from the photo (dominant wall
  colour, medians inside boxes, exposure-corrected).
- 4, 5: the skill asks for an inventory of the photo before the spec, a check item by item after the
  build, and forbids adding what the photo does not show.
- Found on the way: the build script did not reload `rhinospec.naming`, so new categories needed a
  Rhino restart.

Re-run: cmp_b0121 now has the pediment with its relief and oculus, the projecting risalit, the two
giant ionic columns, lesenes, plinth vents, tri hoods and the photo's colours; cmp_b0186 has
full-size windows, no invented mansard, rustication and its colours. Left on those two: round
oculus (11), dormer positions (12), shop sign colour, and two reading slips on b0121 (one hood a bay
off, three arched windows left rectangular) that the after-build check exists to catch.

## Fixed (P2)

- 6: `k:"arcade"` is an open portico arch (rect, arch or seg; `d` = recess depth): the wall is cut,
  and each row of arcades gets a back wall, a ceiling and side returns; doors and windows read
  inside an arch are built on that back wall.
- 7: `rail:"glass"` (panes between slim metal posts, own Glass layer); iron bars 1.6 cm instead of 2 cm.
- 9: `k:"pillar", shape:"round"`: a cylinder standing out of the wall by `d` (free column by
  default), with base and capital in the classic style.
- 10: `style:"modern"` has glass doors and 4 cm frames as well as dark profiles; `k:"spandrel"`.
- 11: `shape:"round"` for windows: an ellipse inscribed in the box, with a ring frame, round glass
  and, in the classic style, a ring surround with a keystone.
- 12: windows read above the eaves of a facade with depth and a pitched roof become dormers at
  those positions; `chimneys` takes x positions in photo pixels.
- 8 stays a reading rule (a second facade part moved forward), now in the skill.
- Found by the fuzzer on the way: a tiny arched door with a wide surround crashed the planner;
  overlapping doors inside one arch broke its back wall. Both fixed, with regression tests.

Re-run: cfp_0003 has an open five-arch portico with columns on the piers and the doors on its back
wall, oval oculi, iron balconies and its stone colours; cfp_0196 has glass parapets between posts,
round piers and glass doors.

## Still open

- Cladding or material by zone (cfp_0196's timber ground floor): a palette has one wall colour.
- Iron railings still read as a dark band from a distance: 12 cm bar spacing is the building-code
  value, and at that density the bars merge in a render.
- Detector classes for porticoes, pediments, modern balconies, spandrels and oculi (13), finials (14 is built now),
  shadowed checking renders (15).

## Second round: five more photos

| photo | type |
|---|---|
| cfp second_26 | three-storey house with a stepped gable (four steps a side), arched windows in the gable and on the upper floor, stone plinth, garage door |
| cfp second_131 | two-storey brick commercial block: parapet raised in the middle, tall sashes and a central round-headed window, dark storefronts under a sign band |
| cfp second_32 | modern white block: dark-framed windows in pairs, small cantilevered balconies with glass parapets staggered floor by floor, downpipes, canopy over the shops |
| cfp second_91 | row of two-storey townhouses: side-gable roof, black shutters, sliding patio doors, brick end units with their gable to the street |
| cfp second_5 | condo in two volumes: brick on a stone base and a taller stone body with a round-headed window and a recessed entrance |

| # | gap | seen in | cause | fix |
|---|---|---|---|---|
| 16 | the wall stops at the eaves: no gable end, stepped gable or raised parapet, and windows in a gable were cut in half with no note | 26, 131, 91 | builder | `top` outline on facades: the wall above the eaves with its openings cut through and a coping; with depth and a gable roof the ridge runs back under the steps |
| 17 | elements cut short by the outline were not reported (only those wholly outside were) | 26, and earlier b0121, cfp_0196 | builder | `notes` also counts elements cut off by more than 5 cm |
| 18 | one colour per family: a stone plinth under brick, dark shop fronts under white sashes, a yellow garage door could not be told apart | 5, 131, 26 | builder | `color` on any element (glass keeps its own), `k:"clad"` material zones with the openings cut through, `palette.clad` |
| 19 | every door was panelled wood: patio doors, glazed entrance doors and garage doors were wrong | 91, 5, 26 | builder | `leaf: panel, glass, garage` on doors |
| 20 | downpipes missing | 32, 91 | builder | `k:"pipe"`: a downpipe on brackets (a gutter when wider than tall) |
| 21 | glass balcony parapets took the dark window glass colour | 32 | builder | they take the `railings` colour |
| 22 | reading slips: a round-headed window read as rectangular, a brick end unit left out | 5, 91 | reading | the inventory catches them; the skill now names the outline, zones, door leaves and pipes |

Re-run: second_26 has its stepped gable with the three arched windows, the stone plinth and a sectional
garage door; second_131 its raised parapet and dark storefronts; second_91 glazed patio doors, downpipes
and a brick end unit with its gable; second_5 the stone base, the arched top window and glass doors in
the recessed entrance; second_32 its downpipes and clear glass parapets. 60 random specs using the new
keys built in Rhino with no failure; a cladding zone wholly inside an opening is now skipped instead of
leaving a build warning.

Still open from this round: the podium deck and fence in front of second_32 (site elements), the
townhouses' roof vents and plumbing stacks (too small to matter), brick and stone texture (colour only),
lettering on signs.

## Third round: fuzzing the planner offline

The fuzzer's specs now go through `rhinospec.check` (no Rhino) by the thousand, with one more test: every
building must be a single group of touching parts (`floating` only flags parts that touch nothing).

- The fuzzer gave glazing bars to pediments (rejected) instead of windows: 45 % of its specs were thrown
  away and bars were never stress-tested. Fixed; 9000 specs, no crash.
- Hip and mansard roofs had no roof slab: they started 30 cm above the walls, in the air (the mansard's
  two tiers touched each other, so the check missed it). Every roof now rests on the slab.
- A pediment above the wall's top edge (a grid read by mistake) floated; it is now dropped and noted, and
  so is an oculus inside it.
- 14 closed: `k:"finial"` (`shape` urn, ball or spire), a pedestal and a body of revolution; on the wall's
  top edge it rises above the eaves over the wall thickness, lower down it stands against the wall.
  Built in Rhino 8: valid closed solids, own layer (Finials / Pinnacoli), trim colour of the palette.

Still open from this round: a round pillar with `d` larger than its diameter and its foot above the
ground stands free in the air (only a reading slip produces it; left as is so porticoes on a podium keep
working).

## Fourth round: is the 3D what the spec says, and can it be edited?

Round trip on 60 CMP ground-truth facades (annotation -> spec -> planned solids -> elevation -> IoU
against the annotation, per class): plain and modern reproduce every box (IoU 1.00); classic adds only
what it means to (window and door surrounds, 15 cm outside the opening). Found and fixed:

- Classic pilasters and round columns were wider than their box (base and capital 6 cm out each side):
  the read box is now their widest outline, the shaft set in.
- 40 % of the classic balcony consoles hung over the window or surround below: each console now stops
  above the opening under it, or goes when less than 8 cm is left (0 % left; 12 of 172 balconies keep
  none, those across French windows).

Built in Rhino 8 (`tools/dev/solid_audit.py`: 15 real readings and 40 random specs, 12554 objects):

- Arched and round surrounds and oculus frames were rings of short segments; their union came out
  open and non-manifold (33 objects). Each band is now one prism with the opening cut through it,
  and arched windows got the frame they lacked.
- When an element's union failed, its pieces were stored as one object with several shells (76
  objects). The union is now kept only when it is a closed, manifold solid; otherwise the pieces are
  separate solids in a group named after the element. Clearing a build also removes its groups.
- Floor slabs were spread evenly over the height and showed through the windows (126 crossings on
  cfp_0003 and d_0140): each slab now sits in the nearest band between rows of openings within half a
  storey, and where none is free (a double-height shop or portico) it stops 1.5 m behind the opening.
- Result: 0 open, non-manifold, naked-edge or multi-shell objects, no slab seen through glass, no
  build warning. The same audit on the previous builder finds 58 bad objects and 210 slab hits on four
  of those readings.

## Fifth round: two new photos, read and built

| photo | type |
|---|---|
| cfp_r5a | eclectic upper storeys: three attic pavilions (two triangular pediments, one segmental top), five arched windows with archivolts, paired pilasters, frieze panels; ground floor cut off by the photo |
| cfp_r5b | modern three-storey office: two-storey curtain wall over a glazed entrance with a canopy, punched windows, dark stone base, open carport under the building |

- Pediments on a pavilion and the cornice crowning it were dropped: the outline was measured over the
  element's full width, ends included, so the low parapet beside the pavilion counted. Projecting
  elements (mouldings, cornices, pediments, deco, sills, finials) are now measured over their core,
  their ends free to overhang; openings stay strict.
- Classic windows lost their surround above the eaves (the room above was measured to the eaves, not to
  the outline) and when they reach the facade's foot (no room under them): 2 surrounds for 15 windows on
  cfp_r5a. The room above follows the outline, and with no room below the band is open at the foot,
  as a door's: 15 of 15.
- Rendered views and renders were plain white: the build set colours but no materials. Every layer now
  gets a shared render material of its colour (glass transparent), objects with their own colour get
  theirs; materials are reused by name and the legacy copies Rhino leaves behind are purged on rebuild
  (three rebuilds: 15 render materials, 63 legacy entries, unchanged).
- Flat roofs were drawn as tiled ones (terracotta): their slab has its own layer, Flat roof / Copertura
  piana, in neutral grey; `palette.roof` still applies.
- Found by the connectivity fuzzer on the way: anything read inside a pediment's box was kept above
  the eaves, so a portico read there got its recess built in the air; only windows (oculi), reliefs and
  mouldings live in a pediment now. And an oculus with a deep `d` was lifted onto the tympanum by its
  full `d`, not by the recess actually built (capped by the wall), and floated up to a metre in front
  of it.
- cfp_r5b's curtain wall spans two storeys: the slab behind it is cut back (fourth round), checked in
  Rhino.

Still open: the radiating fanlight bars of cfp_r5a's central window (bars stop at the springing), the
rooftop railing set back on cfp_r5b (no element for it), relief invisible in shadowless views (15).
Audit after this round, in Rhino: 71 specs, 13845 objects, no open, non-manifold or multi-shell object,
no slab seen through glass, no warning; the document is left empty.

## Sixth round: curved modern buildings, one at a time

The facade method reads a flat elevation; a tower whose roof sweeps up to a spike, a sail or a shell
is a volume first. Method for these, the same for every building:

1. Corners: read the corners of every visible face and write their 3D coordinates with the unknown
   sizes as names (`W`, `D`, `H0`), the building's regularity as arithmetic (`Zb+3*F`: equal floors)
   and hidden feet as `?`; `tools/photo3d.py solve` returns the camera and the sizes (rms in pixels).
2. Outlines: the same tool turns every outline read on the photo (a roof line, a profile) into metres
   on its face's plane.
3. Volume: each measured outline is a `prism` through the building; the volume is what they share
   (`keep`, new: a boolean intersection). Skin: the facade (`facade` with the measured `top`) set in
   front of it, its glazing read by `tools/dev/glass_read.py` on the face straightened with the same camera.
4. Check: `tools/silhouette.py compare --calib` draws the model with the photo's own camera, no
   fitting; trees, cars and people are left out of the score. Side by side in Rhino from
   `rhino_view`.

| photo | type |
|---|---|
| The Ascent (styles/Deconstructivism 1634) | residential tower: roof sweeping from the eaves up to a spike on the front corner, side roof falling back from it, free pattern of glass strips on white panels, stacked balconies on the side |

| # | gap | cause | fix |
|---|---|---|---|
| 23 | a curved roofline only raised a thin wall: `top` cuts the facade, the body behind stayed flat at the eaves (silhouette 0.55 with the shape guessed, 0.87 with `top` on measured sizes) | builder | the volume is built from the measured views with `keep`: 0.92 |
| 24 | proportions guessed by eye: the side looked 22-30 m deep in the silhouette fit; the camera solved from the corners gave 22.1 m only once the 14 balconies were tied to equal floors | reading | `photo3d.py`: the camera and sizes from the corners, the building's rules as constraints |
| 25 | `extrude`, `loft` and clockwise `prism` solids came out inside out: a cut with them turned into a union, silently | builder | every extruded, lofted and revolved solid is turned outward (see below) |
| 26 | the facade detector found 0-7 windows on the glass strips (never trained on curtain walls) | detector | `glass_read.py`: colour groups on the straightened face, largest-rectangle cover, 121 panes, 0.81 overlap with the glass |
| 27 | the silhouette score counted trees as missing building | measurement | trees, cars and people are left out (the scene model's classes) |

Result: silhouette 0.936 with the photo's camera (1.4 % of the model outside the building, 5.1 % of
the building not covered), 14 balconies on equal floors, 121 glass panes.

What one photo cannot settle, found on the way and now built into `photo3d.py`:
- Several buildings fit the same corners (a wide one far away, a narrow one close): the tool lists
  them as `alternatives`; `limits` from the brief or the construction (a floor 2.8-4.5 m, about 30
  facade panels of 1.15-2.1 m) rule some out. Choosing by pixel error alone picked a 110 m front.
- A handheld photo is rarely level: the camera now rolls (-2.5 degrees here, error 2.5 -> 1.4 px).
- Published sizes go in `known` (here: roof 89.36 m, 14 to 22 storeys, from Wikipedia, Structurae
  and Libeskind's description).
- Even so the front pulled towards an endless width: its plan is most likely curved, and one view of
  a curved face read as a plane cannot give the plan. The elevation (outline, roof line, floors,
  glazing) is measured; the plan depth stays an assumption, stated as such.

`keep` checked again in Rhino 8.36 after it came back to main (2026-11-06): Rhino's boolean intersection
returned nothing when one solid lay wholly inside the other (a sphere in a box) and when the two
shared faces (two views of one building share its depth and ground), the normal case for `keep`.
The builder now returns the inner solid in the first case and retries with the keep part grown by
10x the tolerance in the second. Volumes against exact ones: box in box 125.0 (125), sphere in box
4.189 (4.189), box in sphere 8.0 (8), front and side views 1606.07 (1605.93), front, side and plan
1403.81 (1403.71), keep with a cut 120.0 (120); separate solids warn and keep the part whole.
Still open: the side face has no glass skin of its own, panel joints are not drawn, the fold of the
front near the spike is flat, and the plan (front curvature, depth) needs a second photo or a plan.

## Already fixed during the trials

- Shutter louvres were one part per slat (2162 parts for b0121, over the limit): one profile now.
- Every element's pieces are joined into one solid per layer (831 -> 233 objects on b0121).
- A deep facade can take a hip or mansard roof, dormers and chimneys (planned as a block).
- Detector duplicates are removed before the draft (172 -> 155 boxes on b0121, IoU unchanged).
- Snapping detector boxes to shared rows and columns was measured and rejected (IoU 0.617 -> 0.610).
- `extrude` and `loft` solids, and `prism`s with a clockwise profile, came out inside out (normals
  pointing in); used in a `cut`, as the part or as the cutter, the difference turned into a union
  without a warning. Every extruded, lofted and revolved solid is now turned outward. Checked in
  Rhino 8: all thirteen primitive types outward, a cut through a clockwise prism removes what it
  should, and `tools/dev/solid_audit.py` on four real readings (1808 objects) finds nothing.
