"""Builds specs in Rhino and checks every object is an editable solid. Runs inside Rhino 8.

From the MCP run_python tool (the script editor injects __rhino_doc__):

    ROOT = r"C:\\...\\claude-rhino-plugin"                       # this repository
    FILES = [r"C:\\...\\data\\work\\cmp_b0121.v3.json", ...]     # spec files to build
    OUT = r"C:\\...\\audit.json"                                 # report
    exec(open(r"C:\\...\\tools\\dev\\solid_audit.py").read())

Each spec is built on the layer rhinospec::AUDIT (cleared before each build, removed at the end).
Per spec the report holds the build's ok/warnings/floating, the object count and, per problem and
layer, how many objects are:
  invalid     not a valid brep
  open        not closed (IsSolid false): holes in the surface, cannot be booleaned
  nonmanifold an edge shared by more than two faces
  naked       naked edges
  multishell  one object holding several separate solids
An editable build has none of them. Also: floor slabs seen through a window, checked by segments
going 1.4 m into the building from each pane ("floor_through_glass").
"""
import collections
import importlib
import json
import os
import sys

R = os.path.join(ROOT, "rhino")  # noqa: F821  (the repository folder, set by the caller)
R in sys.path or sys.path.insert(0, R)

import Rhino  # noqa: E402
import Rhino.Geometry as rg  # noqa: E402
import rhinospec  # noqa: E402
import rhinospec.build  # noqa: E402
import rhinospec.checks  # noqa: E402
import rhinospec.naming  # noqa: E402
import rhinospec.plan  # noqa: E402
import rhinospec.spec  # noqa: E402

for _m in (rhinospec.naming, rhinospec.spec, rhinospec.plan, rhinospec.checks, rhinospec.build, rhinospec):
    importlib.reload(_m)

doc = __rhino_doc__  # noqa: F821
LAYER = "rhinospec::AUDIT"


def _mine():
    return [o for o in doc.Objects if doc.Layers[o.Attributes.LayerIndex].FullPath.startswith(LAYER)]


def _problems(b):
    if b is None or not b.IsValid:
        return ["invalid"]
    out = []
    if not b.IsSolid:
        out.append("open")
    if not b.IsManifold:
        out.append("nonmanifold")
    if b.DuplicateNakedEdgeCurves(True, False):
        out.append("naked")
    comps = b.GetConnectedComponents()
    if comps is not None and len(comps) > 1:
        out.append("multishell")
    return out


def _floor_through_glass(objs):
    tol = doc.ModelAbsoluteTolerance
    s = Rhino.RhinoMath.UnitScale(Rhino.UnitSystem.Meters, doc.ModelUnitSystem)
    path = lambda o: doc.Layers[o.Attributes.LayerIndex].FullPath
    floors = [o.Geometry for o in objs if path(o).endswith(("::Floors", "::Solai"))]
    hits = 0
    for g in objs:
        if not path(g).endswith(("::Glass", "::Vetri")) or "alcon" in path(g):
            continue
        brep = g.Geometry
        for face in brep.Faces:   # sample the pane's large faces, whatever the facade's rotation
            amp = rg.AreaMassProperties.Compute(face)
            if amp is None or amp.Area < 0.25 * brep.GetArea():
                continue
            dom_u, dom_v = face.Domain(0), face.Domain(1)
            for fu in (0.1, 0.5, 0.9):
                for fv in (0.05, 0.5, 0.95):
                    u, v = dom_u.ParameterAt(fu), dom_v.ParameterAt(fv)
                    if face.IsPointOnFace(u, v) == Rhino.Geometry.PointFaceRelation.Exterior:
                        continue
                    p, n = face.PointAt(u, v), face.NormalAt(u, v)
                    if face.OrientationIsReversed:
                        n = -n
                    n.Unitize()
                    ln = rg.LineCurve(p + n * (0.002 * s), p + n * (1.4 * s))   # outward from this face
                    if any(rg.Intersect.Intersection.CurveBrep(ln, fl, tol)[2] for fl in floors):
                        hits += 1
    return hits


def _clean_up():
    groups = set()
    for o in _mine():
        groups.update(o.Attributes.GetGroupList() or [])
        doc.Objects.Delete(o.Id, True)
    for gi in groups:
        if not doc.Groups.GroupMembers(gi):
            doc.Groups.Delete(gi)
    for lay in sorted([l for l in doc.Layers if not l.IsDeleted and l.FullPath.startswith(LAYER)],
                      key=lambda l: -l.FullPath.count("::")):
        doc.Layers.Delete(lay.Index, True)
    # The audit's materials, when nothing else in the document uses them.
    in_use = set(o.RenderMaterial.Id for o in doc.Objects if o.RenderMaterial is not None)
    in_use.update(l.RenderMaterial.Id for l in doc.Layers if not l.IsDeleted and l.RenderMaterial is not None)
    for rm in [m for m in doc.RenderMaterials if m.Name.startswith("rhinospec ") and m.Id not in in_use]:
        doc.RenderMaterials.Remove(rm)
    rhinospec.build._purge_materials(doc)


_clean_up()   # leftovers of an interrupted run would overlap the first build
report = {}
for path in FILES:  # noqa: F821
    spec = json.load(open(path, encoding="utf-8"))
    spec["layer"], spec["clear"] = "AUDIT", True
    out = json.loads(rhinospec.run(json.dumps(spec), doc, redraw=False))
    rec = {"ok": out.get("ok"), "error": out.get("error"), "warnings": out.get("warnings", []),
           "floating": out.get("floating_examples"), "bad": collections.Counter(), "examples": {}}
    objs = _mine()
    for o in objs:
        g = o.Geometry
        b = g if isinstance(g, rg.Brep) else (g.ToBrep() if hasattr(g, "ToBrep") else None)
        where = doc.Layers[o.Attributes.LayerIndex].FullPath[len(LAYER) + 2:]
        for pr in _problems(b):
            key = "%s @ %s" % (pr, where)
            rec["bad"][key] += 1
            rec["examples"].setdefault(key, o.Attributes.Name)
    rec["bad"] = dict(rec["bad"])
    rec["objects"] = len(objs)
    rec["floor_through_glass"] = _floor_through_glass(objs)
    report[os.path.basename(path)] = rec
_clean_up()
doc.Views.Redraw()
json.dump(report, open(OUT, "w"), indent=1)  # noqa: F821
bad = sum(sum(r["bad"].values()) for r in report.values())
print(json.dumps({"specs": len(report), "objects": sum(r["objects"] for r in report.values()), "bad_objects": bad,
                  "floor_through_glass": sum(r["floor_through_glass"] for r in report.values()),
                  "warnings": sum(len(r["warnings"]) for r in report.values()),
                  "failed": [k for k, r in report.items() if not r["ok"]]}))
