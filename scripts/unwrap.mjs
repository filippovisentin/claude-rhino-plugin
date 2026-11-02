// rhino-mcp-router 0.3.0 nests image results: the real MCP content array (text metadata plus an
// image) arrives JSON-encoded inside a single text item, so clients see a huge text blob instead
// of an image. These helpers restore the inner content array.
//
// Router output can carry document data (object names, printed strings), so the unwrap is strict:
// it only fires when the inner array holds at least one image, and every item is rebuilt from
// known fields. Text that merely looks like {"content":...} never gains resource links,
// annotations or other structure.

const IMAGE_MIME = /^image\/[a-z0-9.+-]+$/i;
const BASE64 = /^[A-Za-z0-9+/]+={0,2}$/;

function rebuildItem(x) {
  if (!x || typeof x !== "object") return null;
  if (x.type === "text" && typeof x.text === "string") return { type: "text", text: x.text };
  if (x.type === "image" && typeof x.data === "string" && typeof x.mimeType === "string" &&
      IMAGE_MIME.test(x.mimeType) && BASE64.test(x.data)) {
    return { type: "image", data: x.data, mimeType: x.mimeType };
  }
  return null;
}

// Returns the unwrapped tool result, or null when the result is not a nested image result.
export function unwrapResult(result) {
  const content = result?.content;
  if (!Array.isArray(content) || content.length !== 1 || content[0]?.type !== "text") return null;
  const text = content[0].text;
  if (typeof text !== "string" || !text.startsWith('{"content":')) return null;
  let inner;
  try {
    inner = JSON.parse(text);
  } catch {
    return null;
  }
  if (!Array.isArray(inner.content) || inner.content.length === 0) return null;
  const items = inner.content.map(rebuildItem);
  if (items.some((x) => x === null) || !items.some((x) => x.type === "image")) return null;
  const out = { ...result, content: items };
  if (inner.isError === true) out.isError = true;
  return out;
}

// Transforms one newline-delimited JSON-RPC message from the router. Anything that isn't a
// nested image result is returned unchanged.
export function transformLine(line) {
  // Cheap pre-check: a nested result carries an escaped {"content": somewhere in the line, written
  // either as {\"content\": or, by .NET's encoder in the router, as {"content":.
  if (!line.includes('{\\"content\\":') && !line.includes("{\\u0022content\\u0022:")) return line;
  let msg;
  try {
    msg = JSON.parse(line);
  } catch {
    return line;
  }
  const fixed = unwrapResult(msg?.result);
  if (!fixed) return line;
  return JSON.stringify({ ...msg, result: fixed });
}
