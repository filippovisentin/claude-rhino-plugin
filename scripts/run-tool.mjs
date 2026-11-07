// Runs one of the plugin's runtime tools. Python: the facade detector's (the install made by
// scripts/setup.mjs, else the repo's data/venv-det, or RHINO_FACADE_PYTHON), which also hands over
// the scene model; without a detector, the light Python of setup.mjs --tools or RHINO_TOOLS_PYTHON,
// enough for rectify, crop, overlay, photo3d and silhouette compare (no weights needed):
//   node "<plugin>/scripts/run-tool.mjs" <tool> [args...]
// Only the tools below can run; each argument reaches Python whole, with no shell, Python in
// isolated mode (-I) and Ultralytics offline. The child's output and exit code are passed through;
// errors of this launcher exit with 2.
import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { existsSync } from "node:fs";
import { findDetector } from "./facade-detector.mjs";
import { installDir, VENV_PYTHON } from "./detector-install.mjs";

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
  const det = findDetector(repoRoot, env) ?? toolsPython(env);
  if (!det) {
    return { error: "no Python for the plugin's tools: run node scripts/setup.mjs --tools (light, about 150 MB, no models), " +
      "or node scripts/setup.mjs for the facade detector too (see the README)" };
  }
  const [script, ...fixed] = TOOLS[tool];
  const childEnv = { ...env, YOLO_OFFLINE: "1" };
  if (det.configDir) childEnv.YOLO_CONFIG_DIR = det.configDir;
  if (det.scene) childEnv.RHINO_SCENE_WEIGHTS = det.scene;
  return { python: det.python, args: ["-I", join(repoRoot, "tools", script), ...fixed, ...args.map(String)], env: childEnv };
}

// The light Python for the photo tools: RHINO_TOOLS_PYTHON, else %LOCALAPPDATA%\claude-rhinoenv-tools.
export function toolsPython(env) {
  const python = env.RHINO_TOOLS_PYTHON || join(installDir(env), "venv-tools", ...VENV_PYTHON);
  return existsSync(python) ? { python, configDir: null, scene: null } : null;
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
