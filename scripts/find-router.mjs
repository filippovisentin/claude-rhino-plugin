// Locates rhino-mcp-router from McNeel's Rhino-MCP-Platform package.
// Resolution order: $RHINO_MCP_ROUTER, then the newest installed package version.
import { existsSync, readdirSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

const PACKAGE_NAME = "Rhino-MCP-Platform";

export function packagesRoots() {
  if (process.platform === "win32") {
    const appData = process.env.APPDATA ?? join(homedir(), "AppData", "Roaming");
    return [join(appData, "McNeel", "Rhinoceros", "packages")];
  }
  if (process.platform === "darwin") {
    return [join(homedir(), "Library", "Application Support", "McNeel", "Rhinoceros", "packages")];
  }
  return [];
}

// Semver-style: numeric core first, then a release outranks any prerelease (0.3.0 > 0.3.0-rc1).
export function compareVersions(a, b) {
  const [coreA, preA = ""] = a.split(/-(.*)/s);
  const [coreB, preB = ""] = b.split(/-(.*)/s);
  const pa = coreA.split(".").map((s) => parseInt(s, 10) || 0);
  const pb = coreB.split(".").map((s) => parseInt(s, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  if (preA === preB) return 0;
  if (!preA) return 1;
  if (!preB) return -1;
  return preA.localeCompare(preB, "en", { numeric: true });
}

const subdirs = (dir) => {
  try {
    return readdirSync(dir).filter((n) => statSync(join(dir, n)).isDirectory());
  } catch {
    return [];
  }
};

// Router runtime folders are named like win-x64, win-arm64, osx-arm64.
function runtimeCandidates() {
  const os = process.platform === "win32" ? "win" : process.platform === "darwin" ? "osx" : process.platform;
  const arch = process.arch === "arm64" ? "arm64" : "x64";
  const exe = process.platform === "win32" ? "rhino-mcp-router.exe" : "rhino-mcp-router";
  return [`${os}-${arch}`, `${os}-x64`].map((rid) => ({ rid, exe }));
}

// Returns every installed package version, newest first: [{ rhino, version, dir, router }]
export function findInstalls() {
  const installs = [];
  for (const root of packagesRoots()) {
    for (const rhino of subdirs(root)) {
      const pkgDir = join(root, rhino, PACKAGE_NAME);
      for (const version of subdirs(pkgDir)) {
        const dir = join(pkgDir, version);
        let router = null;
        for (const { rid, exe } of runtimeCandidates()) {
          const p = join(dir, "router", rid, exe);
          if (existsSync(p)) { router = p; break; }
        }
        installs.push({ rhino, version, dir, router });
      }
    }
  }
  return installs.sort((a, b) => compareVersions(b.version, a.version) || compareVersions(b.rhino, a.rhino));
}

export function findRouter() {
  const override = process.env.RHINO_MCP_ROUTER;
  if (override) return existsSync(override) ? override : null;
  return findInstalls().find((i) => i.router)?.router ?? null;
}
