import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { cp, mkdir, rm } from "node:fs/promises";
import { basename, delimiter, join, relative, resolve, sep } from "node:path";
import { resolveReleaseManifest } from "./release-manifest.mjs";
import { collectPluginBackendModules } from "./runtime-plugin-modules.mjs";

const releaseManifest = resolveReleaseManifest();
const { backendRoot, repositoryRoot } = releaseManifest;
const runtimeRoot = releaseManifest.runtimeOutput;
const workRoot = releaseManifest.pyinstallerWork;
const python = resolve(repositoryRoot, ".venv", "Scripts", "python.exe");
if (!existsSync(python)) {
  throw new Error(`Repository Python environment not found: ${python}`);
}

await rm(runtimeRoot, { recursive: true, force: true });
await rm(workRoot, { recursive: true, force: true });
await mkdir(runtimeRoot, { recursive: true });

// Plugin packages keep their own `tests/` alongside their source (see
// plugins/<id>/tests/), so a plain directory copy would ship pytest-only
// modules (~925K) to end users. Stage a filtered copy of `plugins/` that
// drops each plugin's `tests/` directory and `__pycache__`, then point
// PyInstaller at the staging copy instead of the real source tree.
const stagingRoot = resolve(workRoot, "plugins-staging");
await mkdir(stagingRoot, { recursive: true });
const stagedPluginsDir = join(stagingRoot, "plugins");
const pluginsSourceDir = join(repositoryRoot, "plugins");
await cp(pluginsSourceDir, stagedPluginsDir, {
  recursive: true,
  filter: (source) => {
    if (basename(source) === "__pycache__") return false;
    // Only drop the plugin-level `plugins/<id>/tests/` directory (and its
    // contents), matched by path depth from the plugins root. A basename-only
    // check would also exclude `plugins/<id>/backend/**/tests` or future
    // `ui/**/tests` directories that are not pytest fixtures.
    const relativePath = relative(pluginsSourceDir, source);
    if (relativePath === "") return true;
    const segments = relativePath.split(sep);
    if (segments.length >= 2 && segments[1] === "tests") return false;
    return true;
  },
});

// Namespace directories have no __init__.py, so collect-submodules("plugins")
// misses their backends. Analyze actual backend modules to retain transitive
// host/third-party dependencies used by dynamically loaded plugin entry points.
const pluginModules = await collectPluginBackendModules(stagedPluginsDir);
const dataSeparator = delimiter;
const args = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onedir",
  "--name",
  "shiori-runtime",
  "--distpath",
  runtimeRoot,
  "--workpath",
  workRoot,
  "--specpath",
  workRoot,
  "--paths",
  backendRoot,
  "--paths",
  stagingRoot,
  // External package admission reads the host distribution's direct runtime
  // requirements without importing them. Preserve that inventory in frozen runs.
  "--recursive-copy-metadata",
  "shiori-agent",
  "--add-data",
  `${stagedPluginsDir}${dataSeparator}plugins`,
  "--add-data",
  `${join(backendRoot, "skills")}${dataSeparator}skills`,
  "--add-data",
  `${join(repositoryRoot, "apps", "desktop", "renderer", "src", "chat", "common_emojis.json")}${dataSeparator}.`,
  "--add-data",
  `${join(repositoryRoot, "config", "examples", "config.example.toml")}${dataSeparator}config/examples`,
  ...pluginModules.flatMap((name) => ["--hidden-import", name]),
  "--collect-submodules",
  "desktop_bridge",
  "--collect-submodules",
  "agent",
  join(backendRoot, "main.py"),
];

const child = spawn(python, args, { cwd: backendRoot, stdio: "inherit" });
child.once("error", (error) => {
  throw new Error(`Unable to start PyInstaller with ${python}: ${error.message}`);
});
const exitCode = await new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
if (exitCode !== 0) {
  throw new Error(`PyInstaller failed with exit code ${exitCode}`);
}
