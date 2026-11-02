// MCP stdio entry point: finds McNeel's rhino-mcp-router and sits between it and the client.
// Client -> router traffic passes through untouched; router -> client messages go through
// transformLine, which restores images the router nests inside text. RHINO_MCP_RAW=1 disables that.
import { spawn } from "node:child_process";
import { findRouter, packagesRoots } from "./find-router.mjs";
import { transformLine } from "./unwrap.mjs";

const router = findRouter();
if (!router) {
  const override = process.env.RHINO_MCP_ROUTER;
  console.error(
    override
      ? `[claude-rhino] RHINO_MCP_ROUTER points to a missing file: ${override}`
      : "[claude-rhino] rhino-mcp-router not found.\n" +
          "Install the 'Rhino-MCP-Platform' package from Rhino's Package Manager (_PackageManager),\n" +
          `or set RHINO_MCP_ROUTER to the router executable. Searched: ${packagesRoots().join(", ") || "(unsupported OS)"}`
  );
  process.exit(1);
}

const raw = process.env.RHINO_MCP_RAW === "1";
const child = spawn(router, process.argv.slice(2), {
  stdio: ["pipe", raw ? "inherit" : "pipe", "inherit"],
  windowsHide: true,
});

child.on("error", (err) => {
  console.error(`[claude-rhino] failed to start ${router}: ${err.message}`);
  process.exit(1);
});
// "close" fires after the child's stdio has drained, so the last response is never cut off.
child.on("close", (code, signal) => process.exit(signal ? 1 : code ?? 0));

// Never leave the router running without us: covers client kill, closed pipes and Windows,
// where SIGTERM handlers don't fire.
process.on("exit", () => child.exitCode === null && child.kill());
for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => child.kill(sig));
process.stdout.on("error", () => child.kill());
process.stdin.on("end", () => setTimeout(() => child.kill(), 3000).unref());

process.stdin.pipe(child.stdin);
child.stdin.on("error", () => {}); // router gone: its close handler reports it

if (!raw) {
  let buf = "";
  const emit = (line) => {
    const clean = line.replace(/\r$/, "");
    const out = transformLine(clean);
    // Unchanged lines keep their exact bytes, including any \r.
    if (!process.stdout.write((out === clean ? line : out) + "\n")) {
      child.stdout.pause();
      process.stdout.once("drain", () => child.stdout.resume());
    }
  };
  child.stdout.setEncoding("utf8");
  child.stdout.on("data", (chunk) => {
    buf += chunk;
    let i;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i);
      buf = buf.slice(i + 1);
      emit(line);
    }
  });
  child.stdout.on("end", () => buf && emit(buf));
}
