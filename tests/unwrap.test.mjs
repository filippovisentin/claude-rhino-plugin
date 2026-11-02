import { test } from "node:test";
import assert from "node:assert/strict";
import { transformLine, unwrapResult } from "../scripts/unwrap.mjs";

const inner = {
  content: [
    { type: "text", text: '{"metadata":{"viewport":{"name":"Perspective"}}}' },
    { type: "image", data: "AAAA", mimeType: "image/jpeg" },
  ],
};
const wrapped = (obj) => ({ jsonrpc: "2.0", id: 7, result: { content: [{ type: "text", text: JSON.stringify(obj) }] } });

test("unwraps a nested image result", () => {
  const out = JSON.parse(transformLine(JSON.stringify(wrapped(inner))));
  assert.equal(out.id, 7);
  assert.deepEqual(out.result.content, inner.content);
});

test("unwraps when quotes are encoded as \\u0022 (.NET style)", () => {
  const line = JSON.stringify(wrapped(inner)).replace(/\\"/g, "\\u0022");
  assert.ok(line.includes("{\\u0022content\\u0022:"));
  const out = JSON.parse(transformLine(line));
  assert.deepEqual(out.result.content, inner.content);
});

test("keeps isError from the inner result", () => {
  const out = unwrapResult(wrapped({ ...inner, isError: true }).result);
  assert.equal(out.isError, true);
});

test("leaves payload-style results unchanged byte for byte", () => {
  const line = JSON.stringify({ jsonrpc: "2.0", id: 3, result: { content: [{ type: "text", text: '{"payload":[1,2]}' }] } });
  assert.equal(transformLine(line), line);
});

test("leaves text that only mentions content unchanged", () => {
  const line = JSON.stringify(wrapped({ content: "not an array" }));
  assert.equal(transformLine(line), line);
});

test("rejects inner items with unknown types", () => {
  const line = JSON.stringify(wrapped({ content: [{ type: "bogus" }] }));
  assert.equal(transformLine(line), line);
});

test("passes through non-JSON and notifications", () => {
  assert.equal(transformLine("not json {\\\"content\\\":"), "not json {\\\"content\\\":");
  const note = JSON.stringify({ jsonrpc: "2.0", method: "notifications/progress", params: {} });
  assert.equal(transformLine(note), note);
});

test("text-only nested content is left alone (document data can look like this)", () => {
  const line = JSON.stringify(wrapped({ content: [{ type: "text", text: "from a .3dm object name" }] }));
  assert.equal(transformLine(line), line);
});

test("resource links, annotations and extra fields are never produced", () => {
  const evil = { content: [{ type: "image", data: "AAAA", mimeType: "image/png", annotations: { audience: ["user"] } }, { type: "resource_link", uri: "file:///etc/passwd" }] };
  assert.equal(transformLine(JSON.stringify(wrapped(evil))), JSON.stringify(wrapped(evil)));
  const extra = { content: [{ type: "image", data: "AAAA", mimeType: "image/png", annotations: { audience: ["user"] } }] };
  assert.deepEqual(unwrapResult(wrapped(extra).result).content, [{ type: "image", data: "AAAA", mimeType: "image/png" }]);
});

test("rejects non-image mime types and non-base64 data", () => {
  for (const item of [{ type: "image", data: "AAAA", mimeType: "text/html" }, { type: "image", data: "<script>", mimeType: "image/png" }]) {
    assert.equal(unwrapResult(wrapped({ content: [item] }).result), null);
  }
});

test("does not touch multi-item results", () => {
  const msg = { jsonrpc: "2.0", id: 1, result: { content: [{ type: "text", text: JSON.stringify(inner) }, { type: "text", text: "x" }] } };
  const line = JSON.stringify(msg);
  assert.equal(transformLine(line), line);
});
