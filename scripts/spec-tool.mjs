// Adds two MCP tools to the router's list, so any MCP client (Claude Desktop, Claude Code,
// Codex / ChatGPT, Cursor) can model with a JSON spec instead of Python:
//   build_model  validates a rhinospec spec and builds it in Rhino
//   check_model  validates only and reports parts and floating pieces
// A call is rewritten into the router's own run_python call. The spec and the plugin path travel
// base64-encoded inside a fixed script, so nothing the model writes can become Python code.

export const MAX_SPEC_BYTES = 1_000_000;
const SLOT_RE = /^[A-Za-z0-9_.-]{1,64}$/;

const SPEC_DOC = `JSON spec -> Rhino solids. {"units":"mm|cm|m","layer":"Name","clear":true,"parts":[...]}. clear:true replaces the layer's previous build: rebuild the whole spec when iterating. Everything lands on sublayers of "rhinospec".
Every part: type, name, at:[x,y,z], rot (deg about Z through at), tilt:[deg about x, deg about y] (before rot), color "#rrggbb", cut:[parts], group (its own sublayer: always name components). "lang":"it" gives Italian layer names; facades and buildings split into per-category sublayers themselves.
Primitives: box size:[x,y,z] (corner at at) | cyl r,h | cone r,h,r2 | sphere r | torus R,r | extrude pts:[[x,y]..],h | prism pts:[[x,z]..],len (profile in XZ, along +y) | revolve profile:[[r,z]..] | loft sections:[{pts,z}..] | pipe path:[[x,y,z]..] (relative to at),r | panel size:[w,h],t,holes:[[u,v,w,h]..].
array: of:part, n:[nx,ny,nz], step:[dx,dy,dz], turn (deg per copy about pivot:[x,y]: spirals, radial).
building: footprint:[[x,y]..], floors, floor_h, wall_t, slab_t, roof flat|gable|none, roof_h, openings:[{wall,offset,width,height,sill,floor,count,gap}].
facade (elevation from a photo): h (m), px:[x0,y0,x1,y1] facade corners in photo pixels, els:[{k, box:[x0,y0,x1,y1] pixels, grid:[nx,ny,dx,dy] pixel steps or xs:[..],ys:[..] exact column/row starts (tall facades), bars:[v,h], shape, d}], optional depth (builds side/back walls, floors slabs, roof), floors, roof flat|gable|none, roof_h, t, at, rot.
block (whole building, corner photos): w (x), d (y), h, t, floors, roof, roof_h, at, rot, faces:{front,right,back,left: {px, els} as in facade, w/h/t set by the block}; front along +x at y=0, others counter-clockwise, each read as seen from outside. k: window|door|shop (hole+frame+glass, shape rect|arch|seg), cornice (hood above one window, shape flat|tri|seg), molding (horizontal band, d 0.4-0.8 for a main cornice), sill, pillar, balcony, blind (shutter), deco. One box per framed sash; use grid for every regular row/column; hidden windows in a regular rhythm are still there.
Result: one line {"ok":true,"added":n,"bbox":..} plus "floating" when parts touch neither ground nor another part (fix them), or {"ok":false,"error":"path: reason"}: fix that path and rebuild.`;

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

export function createSpecBridge(rhinoDir) {
  const pending = new Map(); // request id -> "list" | "call"
  const key = (id) => JSON.stringify(id);

  // Returns { toRouter, toClient }: the (possibly rewritten) line for the router, or an
  // immediate error reply for the client.
  function fromClient(line) {
    if (!line.includes('"tools/')) return { toRouter: line };
    let msg;
    try { msg = JSON.parse(line); } catch { return { toRouter: line }; }
    if (msg?.method === "tools/list" && msg.id !== undefined) {
      pending.set(key(msg.id), "list");
      return { toRouter: line };
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
      const names = new Set(msg.result.tools.map((t) => t.name));
      msg.result.tools.push(...TOOLS.filter((t) => !names.has(t.name)));
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
