import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { join } from "node:path";

const launcherSource = `"""Build-local argument transport; no command-line parsing or shell expansion."""
import json
from pathlib import Path
from PyInstaller.__main__ import run

run(json.loads(Path(__file__).with_name("arguments.json").read_text(encoding="utf-8")))
`;

/** Preserve the complete PyInstaller vector on disk so Windows receives only a short script path. */
export async function preparePyinstallerInvocation(args, workRoot) {
  if (!Array.isArray(args) || args.some((value) => typeof value !== "string")
    || args[0] !== "-m" || args[1] !== "PyInstaller") {
    throw new Error("Expected a Python -m PyInstaller argument vector");
  }
  await mkdir(workRoot, { recursive: true });
  const directory = await mkdtemp(join(workRoot, "pyinstaller-invocation-"));
  const argumentsFile = join(directory, "arguments.json");
  const launcher = join(directory, "launch.py");
  // run(pyi_args) accepts PyInstaller options, not the Python interpreter's -m prefix.
  await writeFile(argumentsFile, JSON.stringify(args.slice(2)), "utf8");
  await writeFile(launcher, launcherSource, "utf8");
  return { pythonArgs: [launcher], argumentsFile, directory };
}
