import { readdir } from "node:fs/promises";
import { join } from "node:path";

/** Finds Python analysis roots in staged backends, including namespace packages. */
export async function collectPluginBackendModules(pluginsRoot) {
  const modules = [];
  async function visit(directory, prefix) {
    const entries = await readdir(directory, { withFileTypes: true });
    for (const entry of entries) {
      if (entry.isDirectory() && entry.name !== "__pycache__") {
        await visit(join(directory, entry.name), [...prefix, entry.name]);
      } else if (entry.isFile() && entry.name.endsWith(".py")) {
        const name = entry.name.slice(0, -3);
        modules.push((name === "__init__" ? prefix : [...prefix, name]).join("."));
      }
    }
  }
  const plugins = await readdir(pluginsRoot, { withFileTypes: true });
  for (const plugin of plugins) {
    if (!plugin.isDirectory()) continue;
    const packageRoot = join(pluginsRoot, plugin.name);
    const entries = await readdir(packageRoot, { withFileTypes: true });
    if (entries.some((entry) => entry.name === "backend" && entry.isDirectory())) {
      await visit(join(packageRoot, "backend"), ["plugins", plugin.name, "backend"]);
    }
  }
  return modules.sort();
}
