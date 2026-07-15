import { readdir } from "node:fs/promises";
import { spawn } from "node:child_process";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repoRoot = resolve(desktopRoot, "..");
const testRoots = [
  resolve(desktopRoot, "src"),
  resolve(desktopRoot, "renderer", "src"),
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

const testFiles = (await Promise.all(testRoots.map(findTestFiles))).flat().sort();
if (!testFiles.length) {
  throw new Error("no desktop unit tests found");
}

const tsxCli = resolve(repoRoot, "node_modules", "tsx", "dist", "cli.mjs");
const rendererTsconfig = resolve(desktopRoot, "renderer", "tsconfig.json");
const child = spawn(
  process.execPath,
  [tsxCli, "--tsconfig", rendererTsconfig, "--test", ...testFiles],
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
