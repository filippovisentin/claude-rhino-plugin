"""Export objects to GLB keeping names, user text and named materials. Runs inside Rhino 8.

Rhino's own glTF export drops object and material names and user text, which breaks the link
between a model and its bill of materials. This exporter writes one node per part, with the
part's user text in the node "extras", one primitive per material, and named PBR materials
(base colour converted from sRGB to linear, metallic and roughness).

From the MCP run_python tool:

    LAYER_PREFIX = "VACUUM"            # only objects on layers whose full path starts with this
    GROUP_BY = "refdes"                 # user-text key that groups objects into one node (None: one node per object)
    GLB_PATH = r"C:\\...\\model.glb"
    exec(open(r"C:\\...\\tools\\export_glb.py").read())

Units: model units are scaled to metres; Rhino Z up becomes glTF Y up.
Materials: a Rhino material gives its own PBR values. An object without one takes the name of
its layer when that name starts with "MAT_" (e.g. MAT_metal_steel), coloured like the layer,
metallic when a whole word of the name is a metal (so "satin" does not count as "tin").
"""
import json
import struct

METAL_WORDS = {"metal", "chrome", "tin", "nickel", "copper", "steel", "gold", "aluminium", "aluminum", "brass"}


def srgb_to_linear(c):
    """One sRGB channel (0..1) to linear, as glTF baseColorFactor expects."""
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def is_metal_name(name):
    """True when a whole word of a material name (split on '_', '-', spaces) is a metal."""
    words = set(name.lower().replace("-", "_").replace(" ", "_").split("_"))
    return bool(words & METAL_WORDS)


def _run():
    import Rhino
    G = Rhino.Geometry
    doc = __rhino_doc__  # noqa: F821
    scale = Rhino.RhinoMath.UnitScale(doc.ModelUnitSystem, Rhino.UnitSystem.Meters)
    mp = G.MeshingParameters.QualityRenderMesh
    group_by = globals().get("GROUP_BY")

    def leaves(obj, xform):
        g = obj.Geometry
        if isinstance(g, G.InstanceReferenceGeometry):
            idef = doc.InstanceDefinitions.FindId(g.ParentIdefId)
            for o in idef.GetObjects():
                for item in leaves(o, xform * g.Xform):
                    yield item
        else:
            yield g, obj.Attributes, xform

    def to_mesh(g):
        if isinstance(g, G.Mesh):
            return g.DuplicateMesh()
        brep = g.ToBrep() if isinstance(g, G.Extrusion) else g if isinstance(g, G.Brep) else None
        parts = G.Mesh.CreateFromBrep(brep, mp) if brep else None
        if not parts:
            return None
        m = G.Mesh()
        for p in parts:
            m.Append(p)
        return m

    bins, views, accessors, meshes, nodes, materials, mat_index = [], [], [], [], [], [], {}
    offset = [0]

    def view(data, target):
        pad = (-len(data)) % 4
        bins.append(data + b"\x00" * pad)
        views.append({"buffer": 0, "byteOffset": offset[0], "byteLength": len(data), "target": target})
        offset[0] += len(data) + pad
        return len(views) - 1

    def material_id(attr):
        m = None
        if attr.MaterialSource == Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject and attr.MaterialIndex >= 0:
            m = doc.Materials[attr.MaterialIndex]
        elif doc.Layers[attr.LayerIndex].RenderMaterialIndex >= 0:
            m = doc.Materials[doc.Layers[attr.LayerIndex].RenderMaterialIndex]
        lname = doc.Layers[attr.LayerIndex].Name
        name = m.Name if m else (lname if lname.startswith("MAT_") else "MAT_default")
        if name not in mat_index:
            if m:
                pbr = m.PhysicallyBased
                c = pbr.BaseColor if m.IsPhysicallyBased else Rhino.Display.Color4f(m.DiffuseColor)
                metal = pbr.Metallic if m.IsPhysicallyBased else 0.0
                rough = pbr.Roughness if m.IsPhysicallyBased else 0.5
            else:
                col = attr.ObjectColor if attr.ColorSource == Rhino.DocObjects.ObjectColorSource.ColorFromObject else doc.Layers[attr.LayerIndex].Color
                c = Rhino.Display.Color4f(col)
                metal = 1.0 if is_metal_name(name) else 0.0
                rough = 0.25 if metal else 0.45
            materials.append({"name": name, "pbrMetallicRoughness": {
                "baseColorFactor": [srgb_to_linear(ch) for ch in (c.R, c.G, c.B)] + [1.0],
                "metallicFactor": metal, "roughnessFactor": rough}})
            mat_index[name] = len(materials) - 1
        return mat_index[name]

    groups, order = {}, []
    for obj in doc.Objects:
        if obj.IsDeleted or not obj.Visible:
            continue
        layer = doc.Layers[obj.Attributes.LayerIndex].FullPath
        if not layer.startswith(LAYER_PREFIX):  # noqa: F821
            continue
        key = (group_by and obj.Attributes.GetUserString(group_by)) or obj.Attributes.Name or str(obj.Id)
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(obj)

    for key in order:
        by_mat = {}
        for obj in groups[key]:
            for g, attr, x in leaves(obj, G.Transform.Identity):
                m = to_mesh(g)
                if m is None:
                    continue
                m.Transform(x)
                by_mat.setdefault(material_id(attr if attr.LayerIndex >= 0 else obj.Attributes), G.Mesh()).Append(m)
        prims = []
        for mid, m in by_mat.items():
            m.Faces.ConvertQuadsToTriangles()
            m.Normals.ComputeNormals()
            m.Compact()
            pos, nor = [], []
            for i in range(m.Vertices.Count):
                v, n = m.Vertices[i], m.Normals[i]
                pos += [v.X * scale, v.Z * scale, -v.Y * scale]
                nor += [n.X, n.Z, -n.Y]
            idx = [k for f in m.Faces for k in (f.A, f.B, f.C)]
            pa = view(struct.pack("<%df" % len(pos), *pos), 34962)
            accessors.append({"bufferView": pa, "componentType": 5126, "count": m.Vertices.Count, "type": "VEC3",
                              "min": [min(pos[0::3]), min(pos[1::3]), min(pos[2::3])], "max": [max(pos[0::3]), max(pos[1::3]), max(pos[2::3])]})
            na = view(struct.pack("<%df" % len(nor), *nor), 34962)
            accessors.append({"bufferView": na, "componentType": 5126, "count": m.Vertices.Count, "type": "VEC3"})
            ia = view(struct.pack("<%dI" % len(idx), *idx), 34963)
            accessors.append({"bufferView": ia, "componentType": 5125, "count": len(idx), "type": "SCALAR"})
            prims.append({"attributes": {"POSITION": len(accessors) - 3, "NORMAL": len(accessors) - 2}, "indices": len(accessors) - 1, "material": mid})
        if not prims:
            continue
        first = groups[key][0].Attributes
        meshes.append({"name": key, "primitives": prims})
        nodes.append({"name": key, "mesh": len(meshes) - 1, "extras": {k: first.GetUserString(k) for k in first.GetUserStrings().AllKeys}})

    gltf = {"asset": {"version": "2.0", "generator": "claude-rhino-plugin export_glb.py"}, "scene": 0,
            "scenes": [{"nodes": list(range(len(nodes)))}], "nodes": nodes, "meshes": meshes, "materials": materials,
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": offset[0]}]}
    js = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    js += b" " * ((-len(js)) % 4)
    binary = b"".join(bins)
    with open(GLB_PATH, "wb") as f:  # noqa: F821
        f.write(struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(binary)))
        f.write(struct.pack("<II", len(js), 0x4E4F534A) + js)
        f.write(struct.pack("<II", len(binary), 0x004E4942) + binary)
    print({"nodes": len(nodes), "materials": len(materials), "glb": GLB_PATH})  # noqa: F821


if "__rhino_doc__" in globals():
    _run()
