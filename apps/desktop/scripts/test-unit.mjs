import { mkdtemp, readFile, readdir, rm, stat } from "node:fs/promises";
import { spawn } from "node:child_process";
import { availableParallelism, tmpdir } from "node:os";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { batchByArgumentLength } from "./test-unit-batches.mjs";
import { prebundleManifestEnv } from "./test-unit-loader-hooks.mjs";
import { prebundleTestDependencies } from "./test-unit-prebundle.mjs";

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
  // 插件 SDK（#440）的源码与单测同目录并列
  resolve(repoRoot, "packages", "sdk", "src"),
  // 桌宠导出给形象插件的 provider 套件（不在 ui/surface/background 里）
  resolve(repoRoot, "plugins", "desktop_pet", "provider"),
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
// Registers loader hooks in every test process; see test-unit-loader-hooks.mjs.
const testLoader = pathToFileURL(resolve(here, "test-unit-loader.mjs")).href;
// Node runs each file in its own process and defaults to one process fewer
// than the CPUs; the parent mostly waits on its children, so using every CPU
// is measurably faster (#459). Test files stay process-isolated: under
// `--test-isolation=none` module singletons and globals leak between files.
const testConcurrency = availableParallelism();
// Repository-relative paths (the child runs in repoRoot) keep each argument
// short; batching keeps the whole command line under Windows' limit.
const batches = batchByArgumentLength(testFiles.map((path) => relative(repoRoot, path)));

/**
 * Runs one `node --test` batch: spec output goes to the terminal, the summary
 * reporter writes this batch's counts to `summaryPath`.
 */
function runBatch(files, summaryPath, env) {
  return new Promise((resolveBatch, rejectBatch) => {
    const child = runningBatch = spawn(
      process.execPath,
      [tsxCli, "--tsconfig", rendererTsconfig, `--import=${testLoader}`, "--test",
        `--test-concurrency=${testConcurrency}`,
        "--test-reporter=spec", "--test-reporter-destination=stdout",
        `--test-reporter=${summaryReporter}`, `--test-reporter-destination=${summaryPath}`,
        ...(options["test-name-pattern"] !== undefined
          ? [`--test-name-pattern=${options["test-name-pattern"]}`] : []),
        ...files],
      { cwd: repoRoot, stdio: "inherit", env },
    );
    child.on("error", rejectBatch);
    child.on("exit", (code, signal) => {
      runningBatch = undefined;
      resolveBatch({ code, signal });
    });
  });
}

/** The batch process currently running, if any. */
let runningBatch;
/** The interrupt this runner received, once it has received one. */
let interruptSignal;

/**
 * An interrupt must not end this process straight away: the run directory
 * holds the prebundled dependencies and the compile cache, and exiting before
 * the `finally` below removes it leaves the whole thing in the temp directory
 * on every Ctrl+C. Record the signal, pass it to the running batch (Ctrl+C
 * already reaches it through the terminal; a signal sent to this process
 * alone does not), start no further batch, clean up, then end with that
 * signal.
 */
function onInterrupt(signal) {
  interruptSignal ??= signal;
  runningBatch?.kill(signal);
}
const interruptSignals = ["SIGINT", "SIGTERM"];
for (const signal of interruptSignals) process.on(signal, onInterrupt);

// Holds this run's prebundled dependencies and per-batch summaries.
const runDir = await mkdtemp(join(tmpdir(), "shiori-desktop-test-"));
const totals = { tests: 0, passed: 0, failed: 0, skipped: 0, todo: 0 };
const failedBatches = [];
const startedAt = Date.now();
try {
  const childEnv = {
    ...process.env,
    [prebundleManifestEnv]: await prebundleTestDependencies(join(runDir, "prebundle")),
    // Test processes compile the same modules over and over; V8's code cache
    // lets every process after the first skip that. Kept per run unless the
    // caller already chose a cache directory.
    NODE_COMPILE_CACHE: process.env.NODE_COMPILE_CACHE ?? join(runDir, "compile-cache"),
  };
  for (const [index, files] of batches.entries()) {
    if (interruptSignal) break;
    const label = `batch ${index + 1}/${batches.length}`;
    if (batches.length > 1) console.log(`\n[desktop:test] ${label}: ${files.length} files`);
    const summaryPath = join(runDir, `batch-${index + 1}.json`);
    const { code, signal } = await runBatch(files, summaryPath, childEnv);
    if (signal) {
      // The batch was killed (an interrupt, or e.g. the OOM killer): stop
      // instead of starting the next batch, and end with the same signal.
      interruptSignal ??= signal;
      break;
    }
    const counts = JSON.parse(await readFile(summaryPath, "utf-8"));
    for (const key of Object.keys(totals)) totals[key] += counts[key];
    // Every batch runs even after a failure, so one run reports all failures.
    if (code !== 0) failedBatches.push(label);
  }
} finally {
  await rm(runDir, { recursive: true, force: true });
}

if (interruptSignal) {
  for (const signal of interruptSignals) process.off(signal, onInterrupt);
  process.kill(process.pid, interruptSignal);
}

const seconds = ((Date.now() - startedAt) / 1000).toFixed(1);
console.log(`\n[desktop:test] ${testFiles.length} files in ${batches.length} batch(es), ${seconds}s, `
  + `concurrency ${testConcurrency}: tests ${totals.tests}, pass ${totals.passed}, fail ${totals.failed}, `
  + `skipped ${totals.skipped}, todo ${totals.todo}`);
if (failedBatches.length) {
  console.log(`[desktop:test] failed: ${failedBatches.join(", ")}`);
  process.exitCode = 1;
}
