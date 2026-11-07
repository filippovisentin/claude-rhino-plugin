# Assisted photo reconstruction

Needs terminal access and the runtime's light Python (`node scripts/setup.mjs --tools` in `RUNTIME_ROOT`, see runtime.md) for `photo3d` and `silhouette compare`; `silhouette mask` also needs the detector setup's scene model, so without it cut the building out by reading its corners for `photo3d` instead.

`RUNTIME_ROOT` denotes that external installation. For the mesh helper, inspect the existing `tools/export_mesh.py` in that installation and its current arguments before executing it inside Rhino; this package does not install the script.

7. **Curved and free-form buildings** (towers with a sweeping roof, sails, domes, shells): the form matters more than the elements.
   - Scale first: fix metres per pixel from one known size (a stated height, floor count x floor height, a person 1.7 m, a door 2.1 m) and derive every other dimension from the photo with it. Never guess width and height separately. With several faces visible, `node "RUNTIME_ROOT/scripts/run-tool.mjs" photo3d solve` finds the camera and the sizes from the building's corners (equal floors as `Zb+3*F`, hidden feet as `?`, published sizes in `known`) and turns outlines read on the photo into metres; when it lists `alternatives`, add corners or `limits` instead of picking by pixel error.
   - Write each curve as a function (a power curve for a sweeping roof, a superellipse `(1 - t^k)^(1/k)` for a dome, a quarter ellipse for a sail's edge, arcs for a shell's rounded corners) and generate the points from it; no hand-placed control points.
   - The volume follows the outline: a curved roofline is a `prism` of the whole elevation (or a `loft`), not a facade `top` over a flat box, which only raises a thin wall. Read from two views, the volume is the elevation `prism` with `keep:[the side-profile prism]`.
   - Then measure the shape: `node "RUNTIME_ROOT/scripts/run-tool.mjs" silhouette mask` cuts the building out of the photo (`--box` drops fused neighbours), `tools/export_mesh.py` (inside Rhino) exports the model, `node "RUNTIME_ROOT/scripts/run-tool.mjs" silhouette compare ... --search` fits the camera (or `--calib` with `photo3d.py`'s camera) and reports `iou`, `aspect` and the width of each tenth of the height (`bands`, model over photo, top first). Fix the parameter behind the worst band and measure again; report the measured fit for this input without promising a benchmark score. Trees, cars and people in front are left out of the score.


## Interpretation

Use a known physical reference whenever the result is intended to be dimensionally meaningful. If no reference exists, label the output as an assumed-scale reconstruction. Low image residuals or a high silhouette score do not prove the hidden geometry or real-world dimensions.

Do not invent an automatic floor-plan recognizer, photogrammetry pipeline or certified survey feature. Use the main build workflow and [acceptance criteria](acceptance.md).
