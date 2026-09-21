import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { cp, mkdir, rm } from "node:fs/promises";
import { basename, delimiter, join, relative, resolve, sep } from "node:path";
import { prepareBrowserRuntime } from "./browser-runtime.mjs";
import { prepareComputerRuntime } from "./computer-runtime.mjs";
import { resolveReleaseManifest } from "./release-manifest.mjs";
import {
  collectHostBackendModules,
  collectPluginBackendModules,
  collectTopLevelPythonPackageRoots,
} from "./runtime-plugin-modules.mjs";

// 与仓库根 setup.py 的 HOST_PACKAGES 保持一致（该文件是维护基准，修改任一方需
// 同步另一方）。main.py 是下方传给 PyInstaller 的入口脚本本身，不是隐式导入，
// 不在此清单中。
const HOST_PACKAGE_ROOTS = [
  "agent",
  "bootstrap",
  "bus",
  "conversation",
  "core",
  "desktop_bridge",
  "infra",
  "memory2",
  "proactive_v2",
  "prompts",
  "session",
  "shiori_runtime_resources",
  "utils",
];

const releaseManifest = resolveReleaseManifest();
const { backendRoot, repositoryRoot } = releaseManifest;
const browserRuntime = await prepareBrowserRuntime({ repositoryRoot });
const computerRuntime = await prepareComputerRuntime({ repositoryRoot });
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
// pkgutil.iter_modules (which --collect-submodules relies on) silently skips
// implicit namespace subdirectories that lack __init__.py — e.g. agent/tools/.
// That already shipped a real bug (v0.2.0: "No module named
// 'agent.tools.image_generate'", only referenced from a dynamically loaded
// plugin, so static analysis never reached it either). Enumerate host modules
// directly instead of depending on --collect-submodules for these roots.
const hostModules = await collectHostBackendModules(backendRoot, HOST_PACKAGE_ROOTS);

// Build-time completeness assertion (root list): fail loudly if a new
// top-level package shows up under apps/backend that nobody added to
// HOST_PACKAGE_ROOTS. Without this, such a package would never even reach
// collectHostBackendModules above — the exact agent.tools.* failure shape,
// just one level up, and silent (see #315).
const topLevelPythonPackageRoots = await collectTopLevelPythonPackageRoots(backendRoot);
const trackedPackageRoots = new Set(HOST_PACKAGE_ROOTS);
const untrackedPackageRoots = topLevelPythonPackageRoots.filter((name) => !trackedPackageRoots.has(name));
if (untrackedPackageRoots.length > 0) {
  throw new Error(
    `apps/backend 下发现未登记的顶层 Python 包，构建终止：${untrackedPackageRoots.join(", ")}。请将其加入本文件的 HOST_PACKAGE_ROOTS（并同步 setup.py 的 HOST_PACKAGES），如果这些 .py 文件本不该存在，请删除它们。`,
  );
}

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
  `${browserRuntime}${dataSeparator}native/browser-use`,
  "--add-data",
  `${computerRuntime}${dataSeparator}native/computer-use`,
  "--add-data",
  `${join(backendRoot, "skills")}${dataSeparator}skills`,
  "--add-data",
  `${join(repositoryRoot, "apps", "desktop", "renderer", "src", "chat", "common_emojis.json")}${dataSeparator}.`,
  "--add-data",
  `${join(repositoryRoot, "config", "examples", "config.example.toml")}${dataSeparator}config/examples`,
  ...pluginModules.flatMap((name) => ["--hidden-import", name]),
  ...hostModules.flatMap((name) => ["--hidden-import", name]),
  join(backendRoot, "main.py"),
];

// Build-time completeness assertion (disk -> args): fail loudly, before
// PyInstaller even starts, if a tracked host module somehow did not make it
// into the hidden-import argument list. Checks the actual constructed `args`
// array rather than re-deriving the same set, so it also catches future bugs
// in how `args` gets assembled (filtering, dedup, reordering), not just a
// missing collector call.
const hiddenImportValues = new Set(
  args.filter((value, index) => index > 0 && args[index - 1] === "--hidden-import"),
);
const missingHostModules = hostModules.filter((name) => !hiddenImportValues.has(name));
if (missingHostModules.length > 0) {
  throw new Error(
    `以下宿主模块未出现在 PyInstaller 的 --hidden-import 参数中，构建终止：${missingHostModules.join(", ")}`,
  );
}

const child = spawn(python, args, { cwd: backendRoot, stdio: "inherit" });
child.once("error", (error) => {
  throw new Error(`Unable to start PyInstaller with ${python}: ${error.message}`);
});
const exitCode = await new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
if (exitCode !== 0) {
  throw new Error(`PyInstaller failed with exit code ${exitCode}`);
}
