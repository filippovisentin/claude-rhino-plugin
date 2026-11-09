import { test } from "node:test";
import assert from "node:assert/strict";
import { noSlotAdvice, parsePgrep, parseTasklist } from "../scripts/rhino-process.mjs";

test("tasklist CSV gives the Rhino pids", () => {
  const out = '"Rhino.exe","83808","Console","8","1,048,984 K"\r\n"Rhino.exe","1200","Console","8","700,000 K"\r\n';
  assert.deepEqual(parseTasklist(out), [83808, 1200]);
});

test("tasklist with no match gives no pids, in any language", () => {
  assert.deepEqual(parseTasklist("INFO: No tasks are running which match the specified criteria.\r\n"), []);
  assert.deepEqual(parseTasklist("INFORMAZIONI: nessuna attività in esecuzione corrisponde ai criteri specificati.\r\n"), []);
  assert.deepEqual(parseTasklist(""), []);
});

test("pgrep output gives the pids", () => {
  assert.deepEqual(parsePgrep("4211\n977\n"), [4211, 977]);
  assert.deepEqual(parsePgrep(""), []);
});

test("Rhino running without a listener points at MCPStart", () => {
  const msg = noSlotAdvice([83808]);
  assert.match(msg, /pid 83808/);
  assert.match(msg, /MCPStart/);
  assert.match(msg, /Load MCP server at startup/);
});

test("no Rhino process at all asks to start Rhino", () => {
  const msg = noSlotAdvice([]);
  assert.match(msg, /^no running Rhino found/);
  assert.doesNotMatch(msg, /pid/);
});
