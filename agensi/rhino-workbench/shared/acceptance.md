# Acceptance and result interpretation

## Before building

- The target document/slot is unambiguous, units are known and the model layer belongs to this task.
- Known dimensions, guessed dimensions and inferred hidden surfaces are separated.
- A full replacement uses the same dedicated model layer; new unrelated work uses a distinct layer.
- Spec validation succeeds for the intended runtime version. Expanded part count is within its limits.

## After building

Read the actual result fields, including errors, warnings, notes and floating parts. Verify that intended categories and volumes were generated. Compare count/bounding box against the input's order of magnitude; do not treat counts as evidence that the visible shape is correct.

A source-runtime `ok:true` can still contain skipped geometry or failed cuts/intersections with the original solid retained. Resolve consequential warnings before calling a model complete. The builder groups an undo record; this is not a promise of automatic rollback or preservation of the old model on every failure.

The floating check is a plan/bounding-box heuristic, not contact analysis of final Breps. It checks local touching, not a global path to ground; mutually touching suspended components and conservative curved-shape boxes can pass. Its quadratic check is skipped above approximately 1,414 expanded parts. A missing floating report does not certify all parts supported.

For facade work, compare requested floors, bays, openings, roof outline, decorative groups and material zones with the image inventory. Mark clipped/omitted elements. Capture the viewport when the comparison needs it. Do not silently add a neighbouring building, hidden roof or architectural feature the user did not ask to infer.

For calibrated photo work, report known scale, assumptions, residuals and alternative solutions. Silhouette fit describes image agreement, not a complete survey. For free-form models, show what a manual approximation cannot establish when helpers are absent.

Do not describe a mesh as watertight, a model as printable, or an export as saved unless the necessary geometry checks/export actually ran and support that statement. The source mesh helper produces triangle JSON for silhouette comparison; it is not a general STL/STEP/BIM delivery workflow.

## Completion

Summarize:
1. What was built and in which units.
2. Key dimensions and assumed/inferred geometry.
3. Remaining warnings or unavailable checks.
4. Saved paths only for files actually written.

An unsuccessful connection or validation is not a completed build. If an operation fails repeatedly for the same reason, stop that operation and explain the concrete blocker.
