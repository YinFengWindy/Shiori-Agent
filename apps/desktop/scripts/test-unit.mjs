import { mkdtemp, readFile, readdir, rm, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { batchByArgumentLength } from "./test-unit-batches.mjs";

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
const summaryReporter = pathToFileURL(resolve(here, "test-unit-summary-reporter.mjs")).href;
// Repository-relative paths (the child runs in repoRoot) keep each argument
// short; batching keeps the whole command line under Windows' limit.
const batches = batchByArgumentLength(testFiles.map((path) => relative(repoRoot, path)));

/**
 * Runs one `node --test` batch: spec output goes to the terminal, the summary
 * reporter writes this batch's counts to `summaryPath`.
 */
function runBatch(files, summaryPath) {
  return new Promise((resolveBatch, rejectBatch) => {
    const child = spawn(
      process.execPath,
      [tsxCli, "--tsconfig", rendererTsconfig, "--test",
        "--test-reporter=spec", "--test-reporter-destination=stdout",
        `--test-reporter=${summaryReporter}`, `--test-reporter-destination=${summaryPath}`,
        ...(options["test-name-pattern"] !== undefined
          ? [`--test-name-pattern=${options["test-name-pattern"]}`] : []),
        ...files],
      { cwd: repoRoot, stdio: "inherit" },
    );
    child.on("error", rejectBatch);
    child.on("exit", (code, signal) => resolveBatch({ code, signal }));
  });
}

const summaryDir = await mkdtemp(join(tmpdir(), "shiori-desktop-test-"));
const totals = { tests: 0, passed: 0, failed: 0, skipped: 0, todo: 0 };
const failedBatches = [];
const startedAt = Date.now();
try {
  for (const [index, files] of batches.entries()) {
    const label = `batch ${index + 1}/${batches.length}`;
    if (batches.length > 1) console.log(`\n[desktop:test] ${label}: ${files.length} files`);
    const summaryPath = join(summaryDir, `batch-${index + 1}.json`);
    const { code, signal } = await runBatch(files, summaryPath);
    if (signal) {
      // Forward an interrupt (e.g. Ctrl+C) instead of starting the next batch.
      process.kill(process.pid, signal);
      break;
    }
    const counts = JSON.parse(await readFile(summaryPath, "utf-8"));
    for (const key of Object.keys(totals)) totals[key] += counts[key];
    // Every batch runs even after a failure, so one run reports all failures.
    if (code !== 0) failedBatches.push(label);
  }
} finally {
  await rm(summaryDir, { recursive: true, force: true });
}

const seconds = ((Date.now() - startedAt) / 1000).toFixed(1);
console.log(`\n[desktop:test] ${testFiles.length} files in ${batches.length} batch(es), ${seconds}s: `
  + `tests ${totals.tests}, pass ${totals.passed}, fail ${totals.failed}, `
  + `skipped ${totals.skipped}, todo ${totals.todo}`);
if (failedBatches.length) {
  console.log(`[desktop:test] failed: ${failedBatches.join(", ")}`);
  process.exitCode = 1;
}
