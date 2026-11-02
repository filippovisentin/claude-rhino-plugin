# claude-rhino

A Claude Code plugin that connects Claude to **Rhino 8** (and Grasshopper) through McNeel's official **Rhino-MCP-Platform** router.

**New here? Read the two-page overview: [docs/rhino-plugin-overview.pdf](docs/rhino-plugin-overview.pdf)**

It adds:

- **`rhino` MCP server**: a small Node launcher that finds the newest installed `rhino-mcp-router` and runs it over stdio. No version-specific paths in your config, so Rhino package updates don't break it.
- **Viewport images Claude can actually see**: router 0.3.0 returns `get_viewport_image` as one big JSON text block with the image inside it, so Claude gets text instead of a picture, and larger captures exceed the tool-output limit. The launcher unwraps those results into real MCP image content. It only does so when the nested content holds an image, and it rebuilds each item from known fields (`text`, or `image` with an `image/*` type and base64 data), so document text can't turn itself into links or annotations. Every other message passes through unchanged.
- **`rhino-doctor` skill**: a diagnostic script plus a fix table for connection problems, including the classic clash with the community `rhinomcp` package.

> Unofficial. This plugin only launches the router that ships with McNeel's Rhino-MCP-Platform package; it doesn't include or modify it.

## Requirements

- Rhino 8 with the **Rhino-MCP-Platform** package (in Rhino: `_PackageManager`, then search for it)
- Node.js 18 or newer on `PATH`
- Claude Code

Tested on Windows 11 (x64) with Rhino-MCP-Platform 0.3.0. The macOS path lookup is written but not yet tested.

## Install

```bash
claude plugin marketplace add filippovisentin/claude-rhino-plugin
claude plugin install rhino@claude-rhino
```

From a local clone:

```bash
claude plugin marketplace add ./claude-rhino-plugin
claude plugin install rhino@claude-rhino
```

Start a new Claude session afterwards so the MCP server loads.

## Check the connection

```bash
node scripts/doctor.mjs
```

```
[OK  ] node     v24.15.0
[OK  ] package  0.3.0 (Rhino 8.0)
[OK  ] router   C:\Users\you\AppData\Roaming\McNeel\...\rhino-mcp-router.exe
[OK  ] config   no conflicting Rhino MCP entries in ~/.claude.json
[OK  ] mcp      rhino-mcp-router 0.3.0, 32 tools
[OK  ] rhino    Rhino 8 pid 54748 at http://localhost:10500
```

Or just ask Claude: *"Rhino isn't connecting"*. The `rhino-doctor` skill runs the same check.

## Troubleshooting

**`Invalid response frame length 1213486160`**: 1213486160 is the ASCII bytes `HTTP`. Your config runs the community `rhinomcp` (socket protocol) against the Rhino-MCP-Platform HTTP server on port 10500. Remove the old entry:

```bash
claude mcp remove rhino -s user
```

**Router in a non-standard place**: set `RHINO_MCP_ROUTER` to the full path of `rhino-mcp-router(.exe)`.

**Viewport image shows up as text**: you are on plugin 0.1.x, or the session started before the update. Start a new Claude session. To compare with the router's unmodified output, set `RHINO_MCP_RAW=1`.

## Security notes

- The router's `run_python`, `run_csharp` and `run_command` tools run arbitrary code inside Rhino. That is their purpose; keep Claude Code's permission prompts on for them unless you trust the session.
- Text from Rhino documents (object names, user text, files from others) reaches Claude through tool results. Treat models from untrusted sources like any untrusted input.
- `doctor.mjs` prints only the name and executable of other MCP entries, never their arguments or environment, since those can hold API keys.
- Open questions about McNeel's closed-source router and Rhino's HTTP listener on `localhost:10500`, not answerable from this repository: whether it checks `Origin` against browser requests, whether router and Rhino share a secret, and whether the router verifies it is talking to the real Rhino if another process takes the port first.

## Development

```bash
npm test
```

Runs the tests with `node --test` and no dependencies: result unwrapping, version ordering, config conflict detection, and the launcher's stdio framing against a fake router.

## License

MIT
