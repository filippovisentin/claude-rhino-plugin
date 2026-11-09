# -*- coding: utf-8 -*-
"""Rhino side: turns validated primitives into Breps and adds them to the document.

Only runs inside Rhino 8 (RhinoCommon). Everything it builds lands on a sublayer of
ROOT_LAYER, and "clear" only ever deletes objects on that one sublayer, so a spec can never
touch the user's own layers.
"""
from __future__ import division

import math

import Rhino
import Rhino.Geometry as rg

from .naming import layer_color, layer_path
from .plan import OPENING_SHAPES, opening_outline
import System
from System.Collections.Generic import List

ROOT_LAYER = "rhinospec"
UNIT_SYSTEMS = {"mm": Rhino.UnitSystem.Millimeters, "cm": Rhino.UnitSystem.Centimeters, "m": Rhino.UnitSystem.Meters}


MAX_UNION = 40   # larger groups (dentil rows, rusticated bases) are appended, not unioned


def _doc(doc=None):
    if doc is not None:
        return doc
    try:
        import scriptcontext
        if scriptcontext.doc is not None and isinstance(scriptcontext.doc, Rhino.RhinoDoc):
            return scriptcontext.doc
    except Exception:
        pass
    return Rhino.RhinoDoc.ActiveDoc


def _net(cls, items):
    # Explicit .NET lists: Python lists don't always convert to IEnumerable under pythonnet.
    out = List[cls]()
    for x in items:
        out.Add(x)
    return out


def _polyline(points):
    return rg.Polyline(_net(rg.Point3d, points)).ToPolylineCurve()


def _closed_polyline(pts, to3d):
    return _polyline([to3d(p) for p in pts] + [to3d(pts[0])])


def _ccw(pts):
    a = 0.0
    for i in range(len(pts)):
        a += pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
    return pts if a > 0 else list(reversed(pts))


def _outward(brep):
    """A closed brep with its normals pointing out. Extrusions and lofts come out inside-out for
    some windings, and an inside-out solid turns a boolean difference into a union."""
    if brep is not None and brep.IsSolid and brep.SolidOrientation == rg.BrepSolidOrientation.Inward:
        brep.Flip()
    return brep


def _samples(brep):
    """Points on a brep's surface: its vertices and the middle of every face."""
    pts = [v.Location for v in brep.Vertices]
    for f in brep.Faces:
        u, v = f.Domain(0), f.Domain(1)
        pts.append(f.PointAt(u.Mid, v.Mid))
    return pts


def _inside(brep, other, tol):
    """brep lies wholly inside (or on) the closed brep other."""
    return all(other.IsPointInside(pt, tol, False) for pt in _samples(brep))


def _intersect(brep, keep, tol):
    """The intersection of brep and keep, or None when they do not overlap. Rhino's boolean returns nothing in two
    common cases, both handled here: one solid wholly inside the other (no surfaces cross), and
    faces shared by both (two views of one building share its depth and ground): then keep is
    retried enlarged by 10x the tolerance about its centre, which moves the shared faces off the
    plane at the cost of that much accuracy."""
    res = rg.Brep.CreateBooleanIntersection(brep, keep, tol)
    if not res:
        if _inside(brep, keep, tol):
            return brep
        if _inside(keep, brep, tol):
            return keep
        box = keep.GetBoundingBox(True)
        size = max(box.Max.X - box.Min.X, box.Max.Y - box.Min.Y, box.Max.Z - box.Min.Z)
        if size > 0:
            grown = keep.DuplicateBrep()
            grown.Transform(rg.Transform.Scale(box.Center, 1.0 + 20.0 * tol / size))
            res = rg.Brep.CreateBooleanIntersection(brep, grown, tol)
    if not res:
        return None
    return res[0] if len(res) == 1 else max(res, key=lambda b: b.GetVolume())


def _extrude(curve, vec, tol):
    srf = rg.Surface.CreateExtrusion(curve, vec)
    if srf is None:
        return None
    brep = srf.ToBrep()
    capped = brep.CapPlanarHoles(tol)
    return _outward(capped or brep)


def _cap(loft, sections, tol):
    """Caps a loft's open ends. A section edge about as short as the document tolerance (the 1 cm
    ridge of a hip roof in a metre document with 0.01 tolerance) makes CapPlanarHoles return an
    invalid brep, so it is retried with a tolerance well below the shortest edge."""
    capped = loft.CapPlanarHoles(tol)
    if capped is not None and capped.IsValid:
        return capped
    shortest = min(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                   for s in sections for a, b in zip(s["pts"], s["pts"][1:] + s["pts"][:1]))
    if shortest > 0 and shortest / 4.0 < tol:
        capped = loft.CapPlanarHoles(shortest / 4.0)
        if capped is not None and capped.IsValid:
            return capped
    return loft


def _revolve(profile, tol):
    curve = _polyline([rg.Point3d(r, 0, z) for r, z in profile])
    rs = rg.RevSurface.Create(curve, rg.Line(rg.Point3d(0, 0, 0), rg.Point3d(0, 0, 1)))
    if rs is None:
        return None
    brep = rg.Brep.CreateFromRevSurface(rs, False, False)
    if brep is not None and not brep.IsSolid:
        brep = brep.CapPlanarHoles(tol) or brep
    return _outward(brep)


def _local_brep(p, tol):
    t = p["type"]
    if t == "box":
        sx, sy, sz = p["size"]
        return rg.Box(rg.Plane.WorldXY, rg.Interval(0, sx), rg.Interval(0, sy), rg.Interval(0, sz)).ToBrep()
    if t == "cyl":
        return rg.Cylinder(rg.Circle(rg.Plane.WorldXY, p["r"]), p["h"]).ToBrep(True, True)
    if t == "cone":
        prof = [[0, 0], [p["r"], 0], [p["r2"], p["h"]], [0, p["h"]]]
        if p["r2"] == 0:
            prof = [[0, 0], [p["r"], 0], [0, p["h"]]]
        return _revolve(prof, tol)
    if t == "sphere":
        return rg.Sphere(rg.Point3d(0, 0, 0), p["r"]).ToBrep()
    if t == "torus":
        rs = rg.Torus(rg.Plane.WorldXY, p["R"], p["r"]).ToRevSurface()
        return rg.Brep.CreateFromRevSurface(rs, False, False)
    if t == "extrude":
        crv = _closed_polyline(_ccw(p["pts"]), lambda q: rg.Point3d(q[0], q[1], 0))
        return _extrude(crv, rg.Vector3d(0, 0, p["h"]), tol)
    if t == "prism":
        crv = _closed_polyline(p["pts"], lambda q: rg.Point3d(q[0], 0, q[1]))
        return _extrude(crv, rg.Vector3d(0, p["len"], 0), tol)
    if t == "revolve":
        return _revolve(p["profile"], tol)
    if t == "loft":
        curves = [_closed_polyline(_ccw(s["pts"]), lambda q, z=s["z"]: rg.Point3d(q[0], q[1], z))
                  for s in p["sections"]]
        lofts = rg.Brep.CreateFromLoft(_net(rg.Curve, curves), rg.Point3d.Unset, rg.Point3d.Unset, rg.LoftType.Normal, False)
        if not lofts:
            return None
        return _outward(_cap(lofts[0], p["sections"], tol))
    if t == "panel":
        # One planar face with hole loops, extruded: far faster and sturdier than boolean cuts.
        w, h = p["size"]
        xz = lambda q: rg.Point3d(q[0], 0, q[1])
        loops = [_closed_polyline([[0, 0], [w, 0], [w, h], [0, h]], xz)]
        for hole in p["holes"]:
            shape = OPENING_SHAPES[hole[4]] if len(hole) == 5 else "rect"
            loops.append(_closed_polyline(opening_outline(hole[0], hole[1], hole[2], hole[3], shape), xz))
        faces = rg.Brep.CreatePlanarBreps(_net(rg.Curve, loops), tol)
        if not faces or len(faces) != 1:
            return None
        path = rg.LineCurve(rg.Point3d(0, 0, 0), rg.Point3d(0, p["t"], 0))
        return faces[0].Faces[0].CreateExtrusion(path, True)
    if t == "pipe":
        crv = _polyline([rg.Point3d(q[0], q[1], q[2]) for q in p["path"]])
        pipes = rg.Brep.CreatePipe(crv, p["r"], False, rg.PipeCapMode.Round, True, tol, math.radians(1.0))
        return pipes[0] if pipes else None
    return None


def _placed(p, scale, tol):
    brep = _local_brep(p, tol / scale)
    if brep is None:
        return None
    xf = rg.Transform.Scale(rg.Point3d.Origin, scale)
    xf = xf * rg.Transform.Translation(rg.Vector3d(p["at"][0], p["at"][1], p["at"][2]))
    if p["rot"]:
        xf = xf * rg.Transform.Rotation(math.radians(p["rot"]), rg.Vector3d.ZAxis, rg.Point3d.Origin)
    tilt = p.get("tilt")
    if tilt:   # about local x, then local y, before rot: stand a torus up, lay a cylinder down
        if tilt[1]:
            xf = xf * rg.Transform.Rotation(math.radians(tilt[1]), rg.Vector3d.YAxis, rg.Point3d.Origin)
        if tilt[0]:
            xf = xf * rg.Transform.Rotation(math.radians(tilt[0]), rg.Vector3d.XAxis, rg.Point3d.Origin)
    brep.Transform(xf)
    return brep


def _engulfed(brep, cutters):
    """True when one cutter's bounding box contains the part's: the cut leaves nothing."""
    bb = brep.GetBoundingBox(True)
    for c in cutters:
        cb = c.GetBoundingBox(True)
        if cb.Contains(bb.Min) and cb.Contains(bb.Max):
            return True
    return False


def _material(doc, color, glass=False, cache=None):
    """The shared render material for a colour (transparent for glass), made once per document:
    Rendered views and renders show the model's colours, not plain white. A RenderMaterial, so
    every object and layer uses the same one (per-object legacy material indices get copied)."""
    name = "rhinospec %s%s" % (color.lower(), " glass" if glass else "")
    if cache is not None and name in cache:
        return cache[name]
    rm = next((m for m in doc.RenderMaterials if m.Name == name), None)
    if rm is None:
        mat = Rhino.DocObjects.Material()
        mat.Name = name
        mat.DiffuseColor = _color(color)
        if glass:
            mat.Transparency = 0.55
            mat.Reflectivity = 0.25
        rm = Rhino.Render.RenderMaterial.CreateBasicMaterial(mat, doc)
        rm.Name = name
        doc.RenderMaterials.Add(rm)
    if cache is not None:
        cache[name] = rm
    return rm


def _purge_materials(doc):
    """Rhino mirrors every object's render material in the legacy material table and keeps the
    copies after the object is deleted: drop the rhinospec ones nothing uses any more, so
    rebuilding does not grow the document."""
    used = set(o.Attributes.MaterialIndex for o in doc.Objects)
    used.update(l.RenderMaterialIndex for l in doc.Layers if not l.IsDeleted)
    for i in range(doc.Materials.Count - 1, -1, -1):
        m = doc.Materials[i]
        if not m.IsDeleted and i not in used and m.Name.startswith("rhinospec "):
            doc.Materials.DeleteAt(i)


def _layer(doc, segments, color=None, cache=None, glass=False):
    """Index of rhinospec::seg1::seg2..., creating missing levels. The deepest layer gets color and a
    render material of that colour (unless it already has a material, e.g. set by the user)."""
    full = ROOT_LAYER
    parent = None
    idx = -1
    path = [ROOT_LAYER] + list(segments)
    for depth, seg in enumerate(path):
        full = seg if depth == 0 else full + "::" + seg
        if cache is not None and full in cache:
            idx = cache[full]
        else:
            idx = doc.Layers.FindByFullPath(full, -1)
            if idx < 0:
                layer = Rhino.DocObjects.Layer()
                layer.Name = seg
                if parent is not None:
                    layer.ParentLayerId = doc.Layers[parent].Id
                if color and depth == len(path) - 1:
                    layer.Color = _color(color)
                idx = doc.Layers.Add(layer)
                if color and depth == len(path) - 1:
                    doc.Layers[idx].RenderMaterial = _material(doc, color, glass, cache)
            elif color and depth == len(path) - 1 and doc.Layers[idx].RenderMaterial is None:
                # a layer from a build before materials existed
                doc.Layers[idx].RenderMaterial = _material(doc, color, glass, cache)
            if cache is not None:
                cache[full] = idx
        parent = idx
    return idx, full


def _tree_layers(doc, full):
    """Indices of the layer full and every layer below it."""
    prefix = full + "::"
    return [l.Index for l in doc.Layers if not l.IsDeleted and (l.FullPath == full or l.FullPath.startswith(prefix))]


def _color(hexstr):
    return System.Drawing.Color.FromArgb(int(hexstr[1:3], 16), int(hexstr[3:5], 16), int(hexstr[5:7], 16))


def _clean(b):
    """A closed, manifold, valid solid: what Rhino can edit and boolean again."""
    return b is not None and b.IsValid and b.IsSolid and b.IsManifold


def _join(breps, tol):
    """Pieces of one element: one solid when their boolean union is a clean solid (no inner faces),
    else the clean solids the union gives (pieces that do not touch), else the pieces as they are.
    Never one brep holding several shells, nor an open or non-manifold union: the caller groups
    the pieces when there are several, so the element still selects as one."""
    if len(breps) == 1:
        return breps
    if len(breps) <= MAX_UNION:
        u = rg.Brep.CreateBooleanUnion(_net(rg.Brep, breps), tol)
        if u and all(_clean(b) for b in u):
            return list(u)
    return breps


def build(spec, doc=None, redraw=True):
    """Builds a spec already normalised by spec.validate. Returns a small summary dict.

    Pass the MCP script's __rhino_doc__ as doc: scriptcontext.doc may point elsewhere there.
    """
    doc = _doc(doc)
    if doc is None:
        return {"ok": False, "error": "no active Rhino document"}
    tol = doc.ModelAbsoluteTolerance
    scale = Rhino.RhinoMath.UnitScale(UNIT_SYSTEMS[spec["units"]], doc.ModelUnitSystem)
    warnings = []
    cache = {}
    layer_idx, layer_name = _layer(doc, [spec["layer"]], cache=cache)
    lang = spec.get("lang", "en")
    used = set()

    undo = doc.BeginUndoRecord("rhinospec build")
    try:
        removed = 0
        if spec["clear"]:
            # The spec's whole layer tree, and nothing outside it.
            groups = set()
            for li in _tree_layers(doc, layer_name):
                for obj in list(doc.Objects.FindByLayer(doc.Layers[li]) or []):
                    groups.update(obj.Attributes.GetGroupList() or [])
                    if doc.Objects.Delete(obj, True):
                        removed += 1
            for gi in groups:   # the groups of the previous build, now empty
                if not doc.Groups.GroupMembers(gi):
                    doc.Groups.Delete(gi)
            _purge_materials(doc)

        bbox = rg.BoundingBox.Empty
        ids = []
        joined = {}   # (join, layer, colour) -> [attrs, breps]: one solid per element and layer
        order = []
        for i, p in enumerate(spec["parts"]):
            label = p.get("name") or "parts[%d] %s" % (i, p["type"])
            brep = _placed(p, scale, tol)
            if brep is None or not brep.IsValid:
                warnings.append("%s: geometry failed, skipped" % label)
                continue
            if p.get("keep"):
                # intersection, one keep part at a time: a volume read from several views
                # (an elevation extruded through a side profile and a plan) is what they share
                for k in p["keep"]:
                    kb = _placed(k, scale, tol)
                    res = _intersect(brep, kb, tol) if kb is not None else None
                    if res is None:
                        warnings.append("%s: keep failed, kept whole" % label)
                        break
                    brep = res
            pieces = [brep]
            if p.get("cut"):
                cutters = [c for c in (_placed(c, scale, tol) for c in p["cut"]) if c is not None]
                diff = None
                if cutters:
                    diff = rg.Brep.CreateBooleanDifference(_net(rg.Brep, [brep]), _net(rg.Brep, cutters), tol)
                if diff:
                    pieces = list(diff)  # a cut can split a part: keep every piece
                elif diff is not None and cutters and _engulfed(brep, cutters):
                    warnings.append("%s: cut removes the whole part, skipped" % label)
                    continue
                else:
                    warnings.append("%s: cut failed, kept uncut" % label)
            attrs = Rhino.DocObjects.ObjectAttributes()
            glass = p.get("cat", "").endswith("glass")
            li, lname = _layer(doc, layer_path(spec["layer"], p, lang), layer_color(p), cache, glass)
            attrs.LayerIndex = li
            used.add(lname)
            if p.get("name"):
                attrs.Name = p["name"]
            if p.get("color"):
                attrs.ColorSource = Rhino.DocObjects.ObjectColorSource.ColorFromObject
                attrs.ObjectColor = _color(p["color"])
                attrs.RenderMaterial = _material(doc, p["color"], glass, cache)
            if p.get("join"):
                key = (p["join"], li, p.get("color"))
                if key not in joined:
                    attrs.Name = p["join"]
                    joined[key] = [attrs, []]
                    order.append(key)
                joined[key][1].extend(pieces)
                continue
            for piece in pieces:
                oid = doc.Objects.AddBrep(piece, attrs)
                if oid == System.Guid.Empty:
                    warnings.append("%s: could not be added" % label)
                    continue
                ids.append(oid)
                # BoundingBox is a .NET struct: an instance Union() would update a copy.
                bbox = rg.BoundingBox.Union(bbox, piece.GetBoundingBox(True))

        for key in order:
            attrs, breps = joined[key]
            mine = []
            for piece in _join(breps, tol):
                oid = doc.Objects.AddBrep(piece, attrs)
                if oid == System.Guid.Empty:
                    warnings.append("%s: could not be added" % key[0])
                    continue
                mine.append(oid)
                bbox = rg.BoundingBox.Union(bbox, piece.GetBoundingBox(True))
            if len(mine) > 1:   # one element, several solids: a group selects them together
                doc.Groups.Add(_net(System.Guid, mine))
            ids.extend(mine)

        # Redrawing makes Rhino mesh everything and print "Creating meshes...": skip it in batches.
        if redraw:
            view = doc.Views.ActiveView
            if ids and view is not None:
                view.ActiveViewport.ZoomBoundingBox(bbox)
            doc.Views.Redraw()
    finally:
        doc.EndUndoRecord(undo)

    r3 = lambda pt: [round(pt.X, 3), round(pt.Y, 3), round(pt.Z, 3)]
    out = {"ok": True, "layer": layer_name, "added": len(ids), "removed": removed,
           "layers": len(used), "units": str(doc.ModelUnitSystem)}
    if ids:
        out["bbox"] = [r3(bbox.Min), r3(bbox.Max)]
    if warnings:
        out["warnings"] = warnings[:20]
        if len(warnings) > 20:
            out["warnings"].append("... %d more" % (len(warnings) - 20))
    return out
