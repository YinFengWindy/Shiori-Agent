import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, rm } from "node:fs/promises";
import { delimiter, join, resolve } from "node:path";
import { resolveReleaseManifest } from "./release-manifest.mjs";

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
  "--add-data",
  `${join(backendRoot, "plugins")}${dataSeparator}plugins`,
  "--add-data",
  `${join(backendRoot, "skills")}${dataSeparator}skills`,
  "--add-data",
  `${join(repositoryRoot, "apps", "desktop", "renderer", "src", "chat", "common_emojis.json")}${dataSeparator}common_emojis.json`,
  "--collect-submodules",
  "plugins",
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
