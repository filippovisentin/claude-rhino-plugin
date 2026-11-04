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
- Detector classes for porticoes, pediments, modern balconies, spandrels and oculi (13), finials (14),
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

## Already fixed during the trials

- Shutter louvres were one part per slat (2162 parts for b0121, over the limit): one profile now.
- Every element's pieces are joined into one solid per layer (831 -> 233 objects on b0121).
- A deep facade can take a hip or mansard roof, dormers and chimneys (planned as a block).
- Detector duplicates are removed before the draft (172 -> 155 boxes on b0121, IoU unchanged).
- Snapping detector boxes to shared rows and columns was measured and rejected (IoU 0.617 -> 0.610).
