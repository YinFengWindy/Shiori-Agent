import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveReleaseOutputDirectory } from "./release-paths.mjs";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const builderCli = resolve(desktopRoot, "node_modules", "electron-builder", "cli.js");
const outputDirectory = resolveReleaseOutputDirectory();
const child = spawn(process.execPath, [
  builderCli,
  "--projectDir",
  desktopRoot,
  `--config.directories.output=${outputDirectory}`,
  "--win",
  "--x64",
  "--publish",
  "never",
], {
  cwd: desktopRoot,
  stdio: "inherit",
});

child.once("error", (error) => {
  throw error;
});
const exitCode = await new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
process.exitCode = exitCode;
