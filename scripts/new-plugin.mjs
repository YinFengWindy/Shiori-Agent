import { execFile } from "node:child_process";
import console from "node:console";
import process from "node:process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { delimiter, dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs, promisify } from "node:util";
import { pluginFiles } from "./plugin-scaffold.mjs";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");

/** Create a complete package without overwriting an existing plugin directory. */
export async function createPlugin({ id, ui = false, root = repository }) {
  if (typeof id !== "string" || !/^[a-z][a-z0-9_]{0,63}$/.test(id)) {
    throw new Error("Plugin id must be a Python identifier: lowercase letters, digits or underscores, starting with a letter (max 64 characters)");
  }
  const parent = join(resolve(root), "plugins");
  await mkdir(parent, { recursive: true });
  const destination = join(parent, id);
  // Exclusive mkdir also rejects existing links; cleanup is only for our new directory.
  await mkdir(destination);
  try {
    for (const [name, content] of Object.entries(pluginFiles(id, ui))) {
      const target = join(destination, name);
      await mkdir(dirname(target), { recursive: true });
      await writeFile(target, content, { encoding: "utf8", flag: "wx" });
    }
    const python = join(repository, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
    const options = { cwd: repository, env: { ...process.env, PYTHONUTF8: "1", PYTHONPATH: [join(repository, "packages/sdk/python"), join(repository, "apps/backend"), repository].join(delimiter) } };
    await promisify(execFile)(python, ["-c", "import sys; from pathlib import Path; from agent.plugin_host.manifest import load_manifest; load_manifest(Path(sys.argv[1]))", destination], options);
    await promisify(execFile)(python, ["-m", "scripts.gen_plugin_rpc", "--plugin", destination], options);
    return destination;
  } catch (error) {
    await rm(destination, { recursive: true, force: true });
    throw error;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { values, positionals } = parseArgs({ options: { ui: { type: "boolean", default: false } }, allowPositionals: true });
  if (positionals.length !== 1) throw new Error("Usage: pnpm new-plugin <id> [--ui]");
  console.log(await createPlugin({ id: positionals[0], ui: values.ui }));
}
