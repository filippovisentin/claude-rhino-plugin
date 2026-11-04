// Adds two MCP tools to the router's list, so any MCP client (Claude Desktop, Claude Code,
// Codex / ChatGPT, Cursor) can model with a JSON spec instead of Python:
//   build_model  validates a rhinospec spec and builds it in Rhino
//   check_model  validates only and reports parts and floating pieces
//   detect_facade  (when a trained detector is installed) runs it locally on a photo, see
//                  facade-detector.mjs; it never reaches the router.
// A build/check call is rewritten into the router's own run_python call. The spec and the plugin path travel
// base64-encoded inside a fixed script, so nothing the model writes can become Python code.

import { DETECT_TOOL, checkConf, checkImage, runDetector } from "./facade-detector.mjs";

export const MAX_SPEC_BYTES = 1_000_000;
const SLOT_RE = /^[A-Za-z0-9_.-]{1,64}$/;

const SPEC_DOC = `JSON spec -> Rhino solids. {"units":"mm|cm|m","layer":"Name","clear":true,"parts":[...]}. clear:true replaces the layer's previous build (rebuild the whole spec when iterating).
Every part: type, name, at:[x,y,z], rot (deg about Z through at), tilt:[deg about x, deg about y] (before rot), color "#rrggbb", cut:[parts], group (own sublayer: always name components). "lang":"it": Italian layer names.
Primitives: box size:[x,y,z] (corner at at) | cyl r,h | cone r,h,r2 | sphere r | torus R,r | extrude pts:[[x,y]..],h | prism pts:[[x,z]..],len (profile in XZ, along +y) | revolve profile:[[r,z]..] | loft sections:[{pts,z}..] | pipe path:[[x,y,z]..] (relative to at),r | panel size:[w,h],t,holes:[[u,v,w,h]..].
array: of:part, n:[nx,ny,nz], step:[dx,dy,dz], turn (deg per copy about pivot:[x,y]: spirals, radial).
building: footprint:[[x,y]..], floors, floor_h, wall_t, slab_t, roof, roof_h, openings:[{wall,offset,width,height,sill,floor,count,gap}].
column: order tuscan|doric|ionic|corinthian, h, d (default h/7..h/10), count, spacing, axis x|y (colonnades).
stair: kind straight (w, tread, climbs +y) | spiral (r, core, step deg), h, rail both|left|right|outer|none.
facade (elevation from a photo): h (m), px:[x0,y0,x1,y1] facade corners in photo pixels, els:[{k, box:[x0,y0,x1,y1] pixels, grid:[nx,ny,dx,dy] pixel steps or xs:[..],ys:[..] exact column/row starts (tall facades), bars:[v,h], shape, d}], optional depth (builds side/back walls, floors slabs, roof), floors, roof flat|gable|none, roof_h, t, at, rot.
style classic (ornate pre-1940: surrounds, profiles, balustrades, pilasters) | plain (default). sur (surround m), rail balustrade|iron|solid, deco shape console|oval|panel; k rustic (rusticated base), quoin (corner stones).
block (whole building, corner photos): w (x), d (y), h, t, style, floors, roof flat|gable|hip|mansard|none, roof_h, dormers (per long slope), chimneys, at, rot, faces:{front,right,back,left: {px, els} as in facade, w/h/t set by the block}; front along +x at y=0, others counter-clockwise, each read as seen from outside. k: window|door|shop (shape rect|arch|seg), cornice (window crown, shape flat|tri|seg), molding (band; main cornice d 0.6-1.2), sill (with apron), pillar, balcony, blind, deco. One box per framed sash; use grid for every regular row/column; hidden windows in a regular rhythm are still there.
Result: {"ok":true,"added":n,"bbox":..}, plus "floating" parts to fix, or {"ok":false,"error":"path: reason"}.`;

export const TOOLS = [
  {
    name: "build_model",
    description: "Build 3D geometry in Rhino from a compact JSON spec (cheaper and safer than run_python). " + SPEC_DOC,
    inputSchema: {
      type: "object",
      properties: {
        spec: { type: "object", description: "The rhinospec JSON spec." },
        slot: { type: "string", description: "Optional Rhino slot id from spawn_slot." },
      },
      required: ["spec"],
    },
  },
  {
    name: "check_model",
    description: "Validate a rhinospec JSON spec without building: returns part count and floating parts, or the first error. Same spec as build_model.",
    inputSchema: {
      type: "object",
      properties: {
        spec: { type: "object", description: "The rhinospec JSON spec." },
        slot: { type: "string", description: "Optional Rhino slot id from spawn_slot." },
      },
      required: ["spec"],
    },
  },
];
const OUR_TOOLS = new Set(TOOLS.map((t) => t.name));

// Safe mode (launch-router --safe, used by the Rhino panel): only these tools are listed or
// callable. Everything that runs code or touches files is left out: run_python, run_csharp,
// run_command (Rhino commands can run scripts), Grasshopper graphs (script components),
// open/save/close_doc and slot management. build_model still reaches run_python, but only as
// the fixed script this module writes.
export const SAFE_TOOLS = new Set([
  "build_model", "check_model", "get_context", "list_objects", "get_selection", "set_selection",
  "get_viewport_image", "set_camera", "zoom_to_layer", "zoom_to_object", "set_layer_material",
  "list_slots", "ask_user", "detect_facade",
]);

const b64 = (s) => Buffer.from(s, "utf8").toString("base64");

// The only Python this module ever produces. Inputs enter as base64 literals.
export function pythonScript(rhinoDir, specText, fn) {
  if (fn !== "run" && fn !== "check") throw new Error("bad function");
  const call = fn === "run" ? "rhinospec.run(s, __rhino_doc__)" : "rhinospec.check(s)";
  return [
    "import sys, base64, importlib",
    `p = base64.b64decode("${b64(rhinoDir)}").decode("utf-8")`,
    "p in sys.path or sys.path.insert(0, p)",
    "import rhinospec, rhinospec.spec, rhinospec.plan, rhinospec.checks",
    "mods = [rhinospec.spec, rhinospec.plan, rhinospec.checks]",
    fn === "run" ? "import rhinospec.build; mods.append(rhinospec.build)" : "",
    "for m in mods + [rhinospec]: importlib.reload(m)  # picks up plugin updates without restarting Rhino",
    `s = base64.b64decode("${b64(specText)}").decode("utf-8")`,
    `print("RHINOSPEC " + ${call})`,
  ].filter(Boolean).join("\n");
}

const errorResult = (id, text) =>
  JSON.stringify({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text }], isError: true } });

// Pulls the "RHINOSPEC {...}" line out of a run_python result, whatever shape the router used
// (text holding JSON with a payload string, or a payload object).
export function extractSummary(result) {
  const texts = [];
  const walk = (v, depth = 0) => {
    if (depth > 6 || v == null) return;
    if (typeof v === "string") {
      // A string that is itself JSON is searched decoded, never as escaped text.
      if (v.startsWith("{")) {
        try { walk(JSON.parse(v), depth + 1); return; } catch { /* plain text */ }
      }
      texts.push(v);
    } else if (Array.isArray(v)) v.forEach((x) => walk(x, depth + 1));
    else if (typeof v === "object") Object.values(v).forEach((x) => walk(x, depth + 1));
  };
  walk(result);
  for (const t of texts) {
    const m = t.match(/RHINOSPEC (\{.*\})/);
    if (m) return m[1];
  }
  return null;
}

const okResult = (id, text) => JSON.stringify({ jsonrpc: "2.0", id, result: { content: [{ type: "text", text }] } });

// detector: from findDetector(), or null to leave detect_facade out. run: injectable for tests.
export function createSpecBridge(rhinoDir, { safe = false, detector = null, run } = {}) {
  const extra = detector ? [DETECT_TOOL] : [];
  const pending = new Map(); // request id -> "list" | "call"
  const key = (id) => JSON.stringify(id);

  // Returns { toRouter, toClient, local }: the (possibly rewritten) line for the router, an
  // immediate reply for the client, or a promise of the reply (detect_facade, run here).
  // toClient null with nothing else: the line is dropped.
  function fromClient(line) {
    // Safe mode parses every line, so escaped method names or batches can't slip past.
    if (!safe && !line.includes('"tools/')) return { toRouter: line };
    let msg;
    try { msg = JSON.parse(line); } catch { return safe ? { toClient: null } : { toRouter: line }; }
    if (safe && (msg === null || typeof msg !== "object" || Array.isArray(msg))) {
      return { toClient: null };
    }
    if (msg?.method === "tools/list" && msg.id !== undefined) {
      pending.set(key(msg.id), "list");
      return { toRouter: line };
    }
    if (safe && msg?.method === "tools/call" && !SAFE_TOOLS.has(msg.params?.name)) {
      return { toClient: errorResult(msg.id ?? null, "tool disabled in safe mode: " + String(msg.params?.name).slice(0, 64)) };
    }
    if (msg?.method === "tools/call" && msg.params?.name === DETECT_TOOL.name) {
      if (!detector) return { toClient: errorResult(msg.id ?? null, "detect_facade: no trained detector installed") };
      const a = msg.params.arguments ?? {};
      let image, conf;
      try { image = checkImage(a.image); conf = checkConf(a.conf); } catch (e) {
        return { toClient: errorResult(msg.id ?? null, "detect_facade: " + e.message) };
      }
      return { local: runDetector(detector, image, conf, run).then((t) => okResult(msg.id, t),
        (e) => errorResult(msg.id, "detect_facade: " + e.message)) };
    }
    if (msg?.method !== "tools/call" || !OUR_TOOLS.has(msg.params?.name)) return { toRouter: line };
    const args = msg.params.arguments ?? {};
    let specText = typeof args.spec === "string" ? args.spec : JSON.stringify(args.spec ?? null);
    if (specText === "null") return { toClient: errorResult(msg.id, "spec is required") };
    if (Buffer.byteLength(specText, "utf8") > MAX_SPEC_BYTES) return { toClient: errorResult(msg.id, "spec larger than 1 MB") };
    const callArgs = { script: pythonScript(rhinoDir, specText, msg.params.name === "build_model" ? "run" : "check") };
    if (args.slot !== undefined) {
      if (typeof args.slot !== "string" || !SLOT_RE.test(args.slot)) return { toClient: errorResult(msg.id, "bad slot id") };
      callArgs.slot = args.slot;
    }
    pending.set(key(msg.id), "call");
    return { toRouter: JSON.stringify({ ...msg, params: { name: "run_python", arguments: callArgs } }) };
  }

  // Returns the line for the client.
  function fromRouter(line) {
    if (pending.size === 0) return line;
    const m = line.match(/^\{"jsonrpc":"2\.0","id":(\d+|"(?:[^"\\]|\\.)*")/) ?? line.match(/"id":(\d+|"(?:[^"\\]|\\.)*")/);
    if (!m || !pending.has(m[1])) return line;
    let msg;
    try { msg = JSON.parse(line); } catch { return line; }
    if (msg.method !== undefined) return line; // a request from the router, not our reply
    const kind = pending.get(key(msg.id));
    if (!kind) return line;
    pending.delete(key(msg.id));
    if (kind === "list" && Array.isArray(msg.result?.tools)) {
      if (safe) msg.result.tools = msg.result.tools.filter((t) => SAFE_TOOLS.has(t.name) && !OUR_TOOLS.has(t.name));
      const names = new Set(msg.result.tools.map((t) => t.name));
      msg.result.tools.push(...TOOLS.concat(extra).filter((t) => !names.has(t.name)));
      return JSON.stringify(msg);
    }
    if (kind === "call" && msg.result) {
      const summary = extractSummary(msg.result);
      if (summary) {
        let ok = true;
        try { ok = JSON.parse(summary).ok !== false; } catch { /* keep the text */ }
        msg.result = { content: [{ type: "text", text: summary }], ...(ok ? {} : { isError: true }) };
      }
      return JSON.stringify(msg);
    }
    return line;
  }

  return { fromClient, fromRouter, pending };
}
