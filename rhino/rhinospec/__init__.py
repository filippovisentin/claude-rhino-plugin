# -*- coding: utf-8 -*-
"""rhinospec: build Rhino geometry from a compact JSON spec.

Inside Rhino (through the MCP run_python tool):

    import sys; sys.path.insert(0, r"<plugin>/rhino")
    import rhinospec; print(rhinospec.run('{"units":"m","parts":[{"type":"box","size":[1,1,1]}]}', __rhino_doc__))

run() always returns one short JSON line, so a build costs a few dozen tokens of output.
"""
import json

from .checks import report
from .spec import SpecError, validate

__all__ = ["run", "check", "validate", "SpecError"]


def _parse(spec):
    if isinstance(spec, dict):
        return spec
    if len(spec) > 1000000:
        raise SpecError("spec: larger than 1 MB")
    try:
        return json.loads(spec)
    except ValueError as e:
        raise SpecError("spec: invalid JSON (%s)" % e)


def check(spec):
    """Validates without Rhino. Returns {"ok", "parts"} or {"ok": false, "error"}."""
    try:
        norm = validate(_parse(spec))
        out = {"ok": True, "parts": len(norm["parts"])}
        out.update(report(norm["parts"], norm["units"]))
        if norm.get("notes"):
            out["notes"] = norm["notes"]
        return json.dumps(out)
    except SpecError as e:
        return json.dumps({"ok": False, "error": str(e)})


def run(spec, doc=None, redraw=True):
    """Validates, then builds in doc (default: the active Rhino document).

    redraw=False skips zoom and redraw, for batches of builds.
    """
    try:
        norm = validate(_parse(spec))
    except SpecError as e:
        return json.dumps({"ok": False, "error": str(e)})
    from .build import build  # imports RhinoCommon, so only inside Rhino
    try:
        out = build(norm, doc, redraw)
        if out.get("ok"):
            out.update(report(norm["parts"], norm["units"]))
            if norm.get("notes"):
                out["notes"] = norm["notes"]
        return json.dumps(out, separators=(",", ":"))
    except Exception as e:  # report, never crash the host script
        return json.dumps({"ok": False, "error": "build: %s: %s" % (type(e).__name__, e)})
