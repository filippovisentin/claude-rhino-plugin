"""Exports every object on a layer (and its sublayers) as one triangle mesh in metres, for
tools/silhouette.py compare. Runs inside Rhino 8.

From the MCP run_python tool (the script editor injects __rhino_doc__):

    LAYER = "rhinospec::Casa"                                  # full layer path
    OUT = r"C:\\...\\casa.mesh.json"
    exec(open(r"C:\\...\\tools\\export_mesh.py").read())

Writes {"v": [[x, y, z], ...], "f": [[i, j, k], ...]} and prints the vertex and face counts.
"""
import json

import Rhino

_doc = __rhino_doc__  # noqa: F821 (injected by Rhino's script editor)
_k = Rhino.RhinoMath.UnitScale(_doc.ModelUnitSystem, Rhino.UnitSystem.Meters)
_mp = Rhino.Geometry.MeshingParameters.FastRenderMesh
_v, _f = [], []
for _o in _doc.Objects:
    _path = _doc.Layers[_o.Attributes.LayerIndex].FullPath
    if not (_path == LAYER or _path.startswith(LAYER + "::")):  # noqa: F821
        continue
    _g = _o.Geometry
    if isinstance(_g, Rhino.Geometry.Extrusion):
        _g = _g.ToBrep()
    _meshes = [_g] if isinstance(_g, Rhino.Geometry.Mesh) else list(Rhino.Geometry.Mesh.CreateFromBrep(_g, _mp) or [])
    for _m in _meshes:
        _m.Faces.ConvertQuadsToTriangles()
        _base = len(_v)
        _v.extend([round(p.X * _k, 4), round(p.Y * _k, 4), round(p.Z * _k, 4)] for p in _m.Vertices)
        _f.extend([_base + fc.A, _base + fc.B, _base + fc.C] for fc in _m.Faces)
with open(OUT, "w") as _fh:  # noqa: F821
    json.dump({"v": _v, "f": _f}, _fh)
print(json.dumps({"layer": LAYER, "vertices": len(_v), "faces": len(_f)}))  # noqa: F821
