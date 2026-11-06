// Runs one of the plugin's runtime tools with the facade detector's Python (the install made by
// scripts/setup.mjs, else the repo's data/venv-det, or RHINO_FACADE_PYTHON):
//   node "<plugin>/scripts/run-tool.mjs" <tool> [args...]
// Only the tools below can run; each argument reaches Python whole, with no shell, Python in
// isolated mode (-I) and Ultralytics offline. The child's output and exit code are passed through;
// errors of this launcher exit with 2.
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { findDetector } from "./facade-detector.mjs";

// tool -> [script in tools/, fixed leading arguments]
export const TOOLS = Object.freeze({
  rectify: ["rectify.py"],
  photo3d: ["photo3d.py"],
  silhouette: ["silhouette.py"],
  overlay: ["photo_tools.py", "overlay"],
  crop: ["photo_tools.py", "crop"],
});

// {python, args, env} to run, or {error} when the tool is not allowed or no Python is installed.
export function toolCommand(repoRoot, env, tool, args) {
  if (typeof tool !== "string" || !Object.hasOwn(TOOLS, tool)) {
    return { error: `unknown tool "${tool}": use one of ${Object.keys(TOOLS).join(", ")}` };
  }
  const det = findDetector(repoRoot, env);
  if (!det) return { error: "no Python for the plugin's tools: run node scripts/setup.mjs first (see the README)" };
  const [script, ...fixed] = TOOLS[tool];
  const childEnv = { ...env, YOLO_OFFLINE: "1" };
  if (det.configDir) childEnv.YOLO_CONFIG_DIR = det.configDir;
  if (det.scene) childEnv.RHINO_SCENE_WEIGHTS = det.scene;
  return { python: det.python, args: ["-I", join(repoRoot, "tools", script), ...fixed, ...args.map(String)], env: childEnv };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const repoRoot = dirname(dirname(fileURLToPath(import.meta.url)));
  const [tool, ...args] = process.argv.slice(2);
  const cmd = toolCommand(repoRoot, process.env, tool, args);
  if (cmd.error) {
    console.error(cmd.error);
    process.exitCode = 2;
  } else {
    const child = spawn(cmd.python, cmd.args, { stdio: "inherit", env: cmd.env, shell: false, windowsHide: true });
    child.on("error", (e) => { console.error(`cannot start ${cmd.python}: ${e.message}`); process.exitCode = 2; });
    child.on("exit", (code, signal) => { process.exitCode = code ?? (signal ? 1 : 0); });
  }
}
