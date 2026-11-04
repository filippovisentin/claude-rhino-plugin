# Standard dimensions for text-to-3D

Sizes to fall back on when a prompt gives none, in metres. Pick the middle of a range unless the
prompt says "small", "large", "low" or "tall". State the assumed size in one line before building.

## People and ergonomics

| Item | Size |
|---|---|
| Standing eye height | 1.6 |
| Seat height | 0.43-0.47 (bar stool 0.75) |
| Table / desk top | 0.72-0.76 (coffee table 0.40-0.45, counter 0.90, bar 1.05) |
| Clear width to walk past | 0.9 |
| Handrail / guard height | 0.9-1.0 (balcony 1.0-1.1) |

## Furniture

| Item | Typical size (w x d x h) | Parts |
|---|---|---|
| Dining chair | 0.45 x 0.50 x 0.85, seat 0.45 high, 0.04 thick | 4 legs 0.035-0.045 square, seat, back 0.40-0.45 above the seat |
| Armchair | 0.80 x 0.85 x 0.80, seat 0.42 | arms 0.60-0.65 high |
| Sofa (3 seats) | 2.10 x 0.90 x 0.85, seat 0.42 | base, 3 cushions, back, arms 0.15-0.25 wide |
| Dining table (4-6) | 1.60 x 0.90 x 0.75, top 0.03-0.04 | legs 0.06-0.08, 0.05-0.10 in from the edges, apron 0.08-0.10 |
| Round table | diameter 1.0-1.2, h 0.75 | one pedestal or 3-4 legs |
| Coffee table | 1.10 x 0.60 x 0.42 | |
| Desk | 1.40 x 0.70 x 0.75 | |
| Bed (double) | 1.60 x 2.00, mattress top 0.50-0.55 | headboard 0.9-1.1 high |
| Wardrobe | 1.0-2.0 x 0.60 x 2.0-2.4 | doors 0.45-0.60 wide |
| Bookcase | 0.80 x 0.30 x 1.80-2.0 | shelves 0.02-0.025, every 0.30-0.38 |
| Kitchen base unit | 0.60 x 0.60 x 0.90 | plinth 0.10-0.15, worktop 0.03-0.04 |
| Floor lamp | h 1.5-1.8, base diameter 0.25-0.35 | shade 0.35-0.45 diameter |
| Table lamp | h 0.45-0.60 | |

## Objects

| Item | Size |
|---|---|
| Mug | diameter 0.08, h 0.095, wall 0.004 |
| Wine glass | h 0.20, bowl diameter 0.08, stem 0.008 |
| Bottle (0.75 l) | diameter 0.075, h 0.30, neck 0.03 |
| Vase | h 0.25-0.40, belly 0.6 of height wide |
| Amphora | h 0.6-0.8, two handles at the shoulder |
| Ring | inner diameter 0.017-0.019, band 0.002 x 0.004 |
| Smartphone | 0.072 x 0.15 x 0.008 |
| Laptop (open) | 0.31 x 0.22 base, screen 0.21 high |

## Architecture

| Item | Size |
|---|---|
| Storey (floor to floor) | houses 2.8-3.0, flats 3.0-3.2, offices 3.5-4.0, historic 3.5-4.5 |
| Wall | interior 0.10-0.15, exterior masonry 0.30-0.50, historic 0.5-0.9 |
| Slab | 0.20-0.30 |
| Door | 0.80-0.90 x 2.10 (front door 1.0-1.2 x 2.2-2.4) |
| Window | 1.0-1.4 x 1.2-1.5, sill 0.9 above the floor; historic 1.1-1.3 x 2.2-2.6 |
| Stair | riser 0.16-0.18, tread 0.27-0.30 (2 risers + 1 tread = 0.62-0.64), width 0.9-1.2 |
| Spiral stair | diameter 1.6-2.2, 20-30 degrees per step, core 0.1-0.2 |
| Ramp | max slope 1:12, width 1.2 |
| Balcony | depth 1.2-1.5, guard 1.0-1.1 |
| Pitched roof | 30-45 degrees (gable rise = half the span x 0.6-1.0) |
| Garage (single) | 3.0 x 6.0 x 2.4 |
| House (single storey) | 10 x 8 footprint, ridge 5-6 |
| Column (classical) | height = 8-10 diameters, capital 1 diameter, base 0.5 diameter |
| Arch | semicircular rise = half the span |

## How to apply

- Decompose into parts named by the user's words ("piano", "gambe", "schienale"), each with its
  own `group`, so the layers read like the object.
- Joints touch: legs end under the top, a shade sits on its stem. `check_model` reports parts
  that float.
- Use `revolve` for turned objects (vases, glasses, columns, lamps), `loft` for tapering forms,
  `array` for repetition (legs, shelves, balusters, steps), `stair` for stairs, `block` or
  `building` for buildings.
