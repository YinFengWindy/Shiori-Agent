import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, rm } from "node:fs/promises";
import { join, resolve } from "node:path";
import { prepareBrowserRuntime } from "./browser-runtime.mjs";
import { prepareComputerRuntime } from "./computer-runtime.mjs";
import { resolveReleaseManifest } from "./release-manifest.mjs";
import { stageBuiltinPlugins } from "./runtime-plugin-staging.mjs";
import { createRuntimePyinstallerArgs } from "./runtime-pyinstaller.mjs";
import { preparePyinstallerInvocation } from "./pyinstaller-invocation.mjs";
import {
  collectHostBackendModules,
  collectPluginBackendModules,
  collectSdkRuntimeModules,
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
await stageBuiltinPlugins(pluginsSourceDir, stagedPluginsDir);

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
// External plugins are installed after shipping; their SDK imports cannot be
// inferred from the builtin dependency graph. Include every runtime SDK module.
const sdkModules = await collectSdkRuntimeModules(join(repositoryRoot, "packages/sdk/python/shiori_sdk"));

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

const args = createRuntimePyinstallerArgs({
  runtimeRoot, workRoot, backendRoot, stagingRoot, stagedPluginsDir,
  browserRuntime, computerRuntime, repositoryRoot, pluginModules, hostModules, sdkModules,
});

const invocation = await preparePyinstallerInvocation(args, workRoot);
const child = spawn(python, invocation.pythonArgs, { cwd: backendRoot, stdio: "inherit" });
const exitCode = await new Promise((resolveExit, reject) => {
  child.once("error", (error) => reject(new Error(`Unable to start PyInstaller with ${python}: ${error.message}`)));
  child.once("exit", (code) => resolveExit(code ?? 1));
});
if (exitCode !== 0) {
  throw new Error(`PyInstaller failed with exit code ${exitCode}`);
}
