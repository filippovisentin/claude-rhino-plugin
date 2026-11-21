"""Clash check between the parts of an assembly. Runs inside Rhino 8.

Parts are the objects grouped by a user-text key (default "refdes"; objects without it are
grouped by name). Each part becomes one merged render mesh (block instances are flattened);
pairs whose bounding boxes overlap are tested with MeshClash. Fast: a few seconds for a few
hundred parts, where testing every mesh against every mesh can run past the MCP time limit.

From the MCP run_python tool:

    LAYER_PREFIX = "VACUUM"                       # only layers whose full path starts with this
    ALLOWED = [["MP2", "pcb_cliff_FL", "board screwed to the chassis"]]   # intended contacts, with the reason
    EXCLUDE = ["MP12"]                             # parts to skip (e.g. a separate product in the file)
    REPORT = r"C:\\...\\interference.json"
    exec(open(r"C:\\...\\tools\\clash_check.py").read())

The report lists interferences and intended contacts separately, each with one clash point.
"""
import json


def boxes_overlap(a, b):
    """a, b: (minx, miny, minz, maxx, maxy, maxz)."""
    return not (a[3] < b[0] or b[3] < a[0] or a[4] < b[1] or b[4] < a[1] or a[5] < b[2] or b[5] < a[2])


def allowed_reason(a, b, allowed):
    """The reason when the pair (a, b) is listed in allowed, in either order; None otherwise."""
    for x, y, why in allowed:
        if (x, y) in ((a, b), (b, a)):
            return why
    return None


def _run():
    import Rhino
    G = Rhino.Geometry
    doc = __rhino_doc__  # noqa: F821
    key_name = globals().get("GROUP_BY", "refdes")
    allowed = globals().get("ALLOWED", [])
    exclude = set(globals().get("EXCLUDE", []))
    mp = G.MeshingParameters.FastRenderMesh

    def leaf_meshes(obj, xform):
        g = obj.Geometry
        if isinstance(g, G.InstanceReferenceGeometry):
            idef = doc.InstanceDefinitions.FindId(g.ParentIdefId)
            for o in idef.GetObjects():
                for m in leaf_meshes(o, xform * g.Xform):
                    yield m
            return
        if isinstance(g, G.Extrusion):
            g = g.ToBrep()
        parts = [g.DuplicateMesh()] if isinstance(g, G.Mesh) else (G.Mesh.CreateFromBrep(g, mp) if isinstance(g, G.Brep) else None)
        for m in parts or []:
            m.Transform(xform)
            yield m

    part_mesh = {}
    for o in doc.Objects:
        if o.IsDeleted or not doc.Layers[o.Attributes.LayerIndex].FullPath.startswith(LAYER_PREFIX):  # noqa: F821
            continue
        key = o.Attributes.GetUserString(key_name) or o.Attributes.Name or str(o.Id)
        if key in exclude:
            continue
        m = part_mesh.setdefault(key, G.Mesh())
        for lm in leaf_meshes(o, G.Transform.Identity):
            m.Append(lm)
    keys = sorted(part_mesh)
    bb = {}
    for k in keys:
        b = part_mesh[k].GetBoundingBox(True)
        bb[k] = (b.Min.X, b.Min.Y, b.Min.Z, b.Max.X, b.Max.Y, b.Max.Z)
    interferences, contacts, checked = [], [], 0
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if not boxes_overlap(bb[a], bb[b]):
                continue
            checked += 1
            hits = G.Intersect.MeshClash.Search(part_mesh[a], part_mesh[b], 0.0, 1)
            if not hits:
                continue
            p = hits[0].ClashPoint
            entry = {"a": a, "b": b, "example": [round(p.X, 2), round(p.Y, 2), round(p.Z, 2)]}
            why = allowed_reason(a, b, allowed)
            if why:
                entry["reason"] = why
                contacts.append(entry)
            else:
                interferences.append(entry)
    out = {"parts": len(keys), "pairs_checked": checked, "interferences": interferences, "intended_contacts": contacts}
    json.dump(out, open(REPORT, "w"), indent=1)  # noqa: F821
    print({"parts": len(keys), "interferences": len(interferences), "contacts": len(contacts), "report": REPORT})  # noqa: F821


if "__rhino_doc__" in globals():
    _run()
