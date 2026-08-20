import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const desktopRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const builder = resolve(desktopRoot, "node_modules", ".bin", process.platform === "win32" ? "electron-builder.cmd" : "electron-builder");
const child = spawn(builder, ["--projectDir", desktopRoot, "--win", "--x64", "--publish", "never"], {
  cwd: desktopRoot,
  stdio: "inherit",
});

child.once("error", (error) => {
  throw error;
});
const exitCode = await new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
process.exitCode = exitCode;
