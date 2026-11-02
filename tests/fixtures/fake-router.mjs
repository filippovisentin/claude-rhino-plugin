// Stand-in for rhino-mcp-router used by the launcher tests. On the first stdin line it writes:
// a nested image result split across chunks, a CRLF-terminated plain line, a ~200 KB line and a
// final line with no trailing newline, then exits.
const nested = JSON.stringify({
  jsonrpc: "2.0",
  id: 1,
  result: { content: [{ type: "text", text: JSON.stringify({ content: [{ type: "text", text: "meta" }, { type: "image", data: "QUJD", mimeType: "image/jpeg" }] }) }] },
});
const big = JSON.stringify({ jsonrpc: "2.0", id: 3, result: { content: [{ type: "text", text: "x".repeat(200_000) }] } });
const last = JSON.stringify({ jsonrpc: "2.0", id: 4, result: { content: [{ type: "text", text: "è last" }] } });

process.stdin.once("data", async () => {
  const half = Math.floor(nested.length / 2);
  process.stdout.write(nested.slice(0, half));
  await new Promise((r) => setTimeout(r, 20));
  process.stdout.write(nested.slice(half) + "\n");
  process.stdout.write('{"jsonrpc":"2.0","id":2,"result":{}}\r\n');
  process.stdout.write(big + "\n");
  process.stdout.write(last, () => process.exit(0));
});
