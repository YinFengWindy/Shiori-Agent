import { readdir, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repoRoot = resolve(desktopRoot, "..", "..");

const { values: options } = parseArgs({
  options: {
    file: { type: "string", multiple: true },
    "test-name-pattern": { type: "string" },
    list: { type: "boolean" },
    help: { type: "boolean" },
  },
});

if (options.help) {
  console.log(`Usage: pnpm test [--file <path-fragment>] [--test-name-pattern <regex>] [--list]

--file may be repeated; matches normalized repository-relative paths (OR).
--test-name-pattern is Node's test-name regex, applied within selected files.
--list prints selected file paths without running tests.
Without filters, all host and plugin unit tests run.`);
  process.exit(0);
}

const fileFilters = (options.file ?? []).map((value) => value.replaceAll("\\", "/"));
if (fileFilters.some((value) => !value.trim())) {
  throw new Error("--file requires a non-empty path fragment");
}
if (options["test-name-pattern"] !== undefined) {
  // Validate before loading tests so a malformed selector fails immediately.
  new RegExp(options["test-name-pattern"]);
}

/**
 * Renderer code owned by plugins rather than by the host.
 *
 * A plugin's `ui/`, `surface/` and `background/` directories are compiled
 * into the renderer bundle (#174, #181, #226) but live outside
 * `apps/desktop/`, so their colocated tests are invisible to a fixed list of
 * desktop test roots. Discovering them here is what keeps moving renderer
 * code into a plugin from silently dropping its coverage.
 */
async function pluginTestRoots() {
  const pluginsRoot = resolve(repoRoot, "plugins");
  let entries;
  try {
    entries = await readdir(pluginsRoot, { withFileTypes: true });
  } catch {
    return [];
  }
  const roots = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    for (const area of ["ui", "surface", "background"]) {
      const candidate = join(pluginsRoot, entry.name, area);
      try {
        if ((await stat(candidate)).isDirectory()) roots.push(candidate);
      } catch {
        // A plugin without that area is the normal case, not a problem.
      }
    }
  }
  return roots;
}

const testRoots = [
  resolve(desktopRoot, "src"),
  resolve(desktopRoot, "renderer", "src"),
  // 跨模块集成回归；e2e 脚本用 *.e2e.ts 命名，不会被这里收集
  resolve(desktopRoot, "tests", "integration"),
  ...(await pluginTestRoots()),
];

async function findTestFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = await Promise.all(entries.map(async (entry) => {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      return await findTestFiles(path);
    }
    return /\.test\.tsx?$/.test(entry.name) ? [path] : [];
  }));
  return files.flat();
}

const testFiles = (await Promise.all(testRoots.map(findTestFiles))).flat().sort()
  .filter((path) => !fileFilters.length || fileFilters.some((filter) =>
    relative(repoRoot, path).replaceAll("\\", "/").includes(filter)));
if (!testFiles.length) {
  throw new Error(`no desktop unit tests found for: ${fileFilters.join(", ")}`);
}
if (options.list) {
  console.log(testFiles.map((path) => relative(repoRoot, path).replaceAll("\\", "/")).join("\n"));
  process.exit(0);
}

const tsxCli = resolve(repoRoot, "node_modules", "tsx", "dist", "cli.mjs");
const rendererTsconfig = resolve(desktopRoot, "renderer", "tsconfig.json");
const child = spawn(
  process.execPath,
  [tsxCli, "--tsconfig", rendererTsconfig, "--test",
    ...(options["test-name-pattern"] !== undefined
      ? [`--test-name-pattern=${options["test-name-pattern"]}`] : []),
    ...testFiles],
  { cwd: repoRoot, stdio: "inherit" },
);

child.on("error", (error) => {
  throw error;
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
    return;
  }
  process.exitCode = code ?? 1;
});
