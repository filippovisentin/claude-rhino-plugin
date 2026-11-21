"""Replace flat placeholder slabs with STEP files (e.g. KiCad board exports). Runs inside Rhino 8.

Model the assembly with simple slabs where the boards go, named like the board (e.g.
"pcb_cliff_FL"), then map each one to a STEP:

    PLACEMENTS = [
        {"name": "pcb_cliff_FL", "step": r"C:\\...\\cliff.step", "facing": [0, 0, -1]},   # components down
        {"name": "pcb_wall_L", "step": r"C:\\...\\wall.step", "facing": "outward"},       # away from the origin
        {"name": "pcb_ui", "step": r"C:\\...\\ui.step"},                                   # default: up (+Z)
    ]
    exec(open(r"C:\\...\\tools\\place_on_placeholder.py").read())

For each placeholder: its largest face gives the board plane, its longest edge in that plane the
board's long axis, its centre the board mid-plane. The STEP is expected as KiCad writes it: board
in XY, bottom face at Z = 0, components on +Z, long side along X; its thickness is read from the
import. "facing" picks which side of the plane the components look to. STEP assemblies arrive as
nested block instances; they are kept as blocks, moved as a whole, and get the placeholder's
layer, name and user text. The placeholder is deleted.
"""


def choose_normal(n, facing, centre):
    """Flip the plane normal n (x, y, z) so the components face 'facing': a vector, 'outward'
    (away from the Z axis through the origin, in plan) or None (up)."""
    if facing == "outward":
        want = (centre[0], centre[1], 0.0)
    elif facing is None:
        want = (0.0, 0.0, 1.0)
    else:
        want = tuple(facing)
    dot = n[0] * want[0] + n[1] * want[1] + n[2] * want[2]
    return tuple(-c for c in n) if dot < 0 else tuple(n)


def _run():
    import Rhino
    G = Rhino.Geometry
    doc = __rhino_doc__  # noqa: F821
    log = []
    for spec in PLACEMENTS:  # noqa: F821
        ph = next((o for o in doc.Objects if o.Attributes.Name == spec["name"] and isinstance(o.Geometry, (G.Brep, G.Extrusion))), None)
        if ph is None:
            log.append("no placeholder %s" % spec["name"])
            continue
        brep = ph.Geometry.ToBrep() if isinstance(ph.Geometry, G.Extrusion) else ph.Geometry
        face = max(brep.Faces, key=lambda f: G.AreaMassProperties.Compute(f.DuplicateFace(False)).Area)
        _, pl = face.TryGetPlane(0.01)
        edges = [e for e in brep.Edges if abs(G.Vector3d(e.PointAtEnd - e.PointAtStart) * pl.Normal) < 0.01]
        long = max(edges, key=lambda e: e.GetLength())
        x = G.Vector3d(long.PointAtEnd - long.PointAtStart)
        x.Unitize()
        c = brep.GetBoundingBox(True).Center
        n = G.Vector3d(*choose_normal((pl.Normal.X, pl.Normal.Y, pl.Normal.Z), spec.get("facing"), (c.X, c.Y, c.Z)))
        before = set(o.Id for o in doc.Objects)
        Rhino.RhinoApp.RunScript('_-Import "%s" _Enter' % spec["step"], False)
        new = [o for o in doc.Objects if o.Id not in before]
        if not new:
            log.append("import failed %s" % spec["step"])
            continue
        bb = G.BoundingBox.Empty
        for o in new:
            bb.Union(o.Geometry.GetBoundingBox(True))
        thick = min(bb.Max.Z - bb.Min.Z, spec.get("board_thickness", 1.6))
        src = G.Plane(G.Point3d(bb.Center.X, bb.Center.Y, 0), G.Vector3d.XAxis, G.Vector3d.YAxis)
        dst = G.Plane(c - n * (thick / 2), x, G.Vector3d.CrossProduct(n, x))
        xf = G.Transform.PlaneToPlane(src, dst)
        for o in new:
            doc.Objects.Transform(o.Id, xf, True)
            o2 = doc.Objects.FindId(o.Id)
            a = ph.Attributes.Duplicate()
            doc.Objects.ModifyAttributes(o2, a, True)
        doc.Objects.Delete(ph, True)
        log.append("%s <- %s (%d objects)" % (spec["name"], spec["step"], len(new)))
    doc.Views.Redraw()
    print("\n".join(log))


if "__rhino_doc__" in globals():
    _run()
