import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, rm } from "node:fs/promises";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");
const repositoryRoot = resolve(desktopRoot, "..");
const runtimeRoot = resolve(repositoryRoot, "release", "runtime");
const workRoot = resolve(repositoryRoot, "release", "pyinstaller-work");
const workspacePython = resolve(repositoryRoot, ".venv", "Scripts", "python.exe");
const python = process.env.PYTHON ?? (existsSync(workspacePython) ? workspacePython : "python");

await rm(runtimeRoot, { recursive: true, force: true });
await rm(workRoot, { recursive: true, force: true });
await mkdir(runtimeRoot, { recursive: true });

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
  repositoryRoot,
  "--add-data",
  `${join(repositoryRoot, "plugins")}${dataSeparator}plugins`,
  "--add-data",
  `${join(repositoryRoot, "skills")}${dataSeparator}skills`,
  "--collect-submodules",
  "plugins",
  "--collect-submodules",
  "desktop_bridge",
  "--collect-submodules",
  "agent",
  join(repositoryRoot, "main.py"),
];

const child = spawn(python, args, { cwd: repositoryRoot, stdio: "inherit" });
child.once("error", (error) => {
  throw new Error(`Unable to start PyInstaller with ${python}: ${error.message}`);
});
const exitCode = await new Promise((resolveExit) => child.once("exit", (code) => resolveExit(code ?? 1)));
if (exitCode !== 0) {
  throw new Error(`PyInstaller failed with exit code ${exitCode}`);
}
