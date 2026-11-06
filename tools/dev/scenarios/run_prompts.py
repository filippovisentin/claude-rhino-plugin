"""Prompt scenarios: each holds a prompt, the spec a model wrote for it and the expected overall
size (spec units). Locally: validity and floating parts. In Rhino (rhino(doc)): builds each one and
compares the real bounding box with the expected size.

  python tools/scenarios/run_prompts.py         local checks only
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "rhino"))
import rhinospec  # noqa: E402


def load():
    with open(os.path.join(HERE, "prompts.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _size_ok(got, want, tol=0.1):
    return all(abs(g - w) <= tol * max(w, 1e-9) for g, w in zip(got, want))


def local():
    rows = []
    for s in load():
        if s["spec"] is None:
            rows.append({"id": s["id"], "status": "not expressible"})
            continue
        text = json.dumps(s["spec"], separators=(",", ":"))
        r = json.loads(rhinospec.check(text))
        rows.append({"id": s["id"], "ok": r["ok"], "parts": r.get("parts"), "floating": r.get("floating", 0),
                     "error": r.get("error"), "spec_chars": len(text)})
    return rows


def rhino(doc, offset_step=30.0):
    import Rhino
    rows = []
    for n, s in enumerate(load()):
        if s["spec"] is None:
            rows.append({"id": s["id"], "status": "not expressible"})
            continue
        spec = s["spec"]
        out = json.loads(rhinospec.run(json.dumps(spec), doc, redraw=False))
        row = {"id": s["id"], "ok": out.get("ok"), "added": out.get("added"), "layers": out.get("layers"),
               "floating": out.get("floating", 0), "warnings": len(out.get("warnings", []))}
        if out.get("ok") and out.get("bbox"):
            k = Rhino.RhinoMath.UnitScale({"mm": Rhino.UnitSystem.Millimeters, "cm": Rhino.UnitSystem.Centimeters,
                                           "m": Rhino.UnitSystem.Meters}[spec["units"]], doc.ModelUnitSystem)
            lo, hi = out["bbox"]
            size = [round((hi[i] - lo[i]) / k, 4) for i in range(3)]
            row["size"] = size
            row["expected"] = s["expect"]["size"]
            row["size_ok"] = _size_ok(size, s["expect"]["size"])
        else:
            row["error"] = out.get("error")
        rows.append(row)
    return rows


if __name__ == "__main__":
    for row in local():
        print(json.dumps(row))
