---
name: rhino-model
description: Build and revise Rhino 8 geometry from text, dimensions, sketches or reference images - furniture, objects, massing, buildings from a footprint, classical columns, stairs - as clean solids on named layers, through a compact JSON spec instead of hand-written code. Uses the free claude-rhino-plugin runtime on the user's PC.
version: "0.2.0"
license: MIT
---

# Rhino modelling from text and dimensions

Requires: Rhino 8 with McNeel Rhino-MCP-Platform; the free claude-rhino-plugin runtime connected to this agent (see runtime.md).

For facades, elevations and whole buildings read from photos or described floor by floor (windows per floor, cornices, balconies), use the rhino-facade skill of this pack instead: its reading rules are needed for a faithful result. This skill brings examples.md, plus the pack's shared runtime.md, spec.md, dimensions.md (sizes to use when the user gives none) and acceptance.md.

## Procedure

1. **Connection.** Check which level of runtime.md is available. With neither dedicated tools nor a usable `run_python`, follow the rhino-doctor skill of this pack.
2. **Dimensions.** Separate what the user gave, what you assume (dimensions.md) and what you infer from an image; one coherent scale per image. Ask only when a missing size changes the design.
3. **Spec.** One compact JSON spec (spec.md): primitives (`box`, `cyl`, `cone`, `sphere`, `torus`, `extrude`, `prism`, `revolve`, `loft`, `pipe`, `panel`), `array` for repeats, `cut`/`keep` for booleans, `building` for a footprint with floors, openings and roof, `column` and `stair` for those elements. `group` on primitives so each component gets its own layer (not on `building`, `facade`, `block`, `column`, `stair`). A layer named after the model; `clear:true` whenever you rebuild it. Never clear layers that belong to other models.
4. **Validate** (`check_model`, or `rhinospec.check` at level 2) and fix the path it reports instead of starting over.
5. **Build** the whole spec in one call. Read warnings, notes and `floating` (acceptance.md) and repair what matters; if the same repair fails twice, report the defect instead of looping.
6. **Look** once at a small viewport image when the tool exists and the task needs a visual check.
7. **Report** sizes, assumptions and anything left unresolved. Save files only where the user asked.

What the spec cannot express (NURBS surfaces from curves, sweeps, fillets) can be written as short RhinoCommon through `run_python`, when the server offers it and the user allows code, on the same layer tree.
