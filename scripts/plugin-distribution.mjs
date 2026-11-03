import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { load } from "js-yaml";

/** Read deployment intent without executing source or requiring built artifacts. */
export async function readPluginManifest(directory) {
  const manifest = load(await readFile(join(directory, "manifest.yaml"), "utf8"));
  if (!manifest || typeof manifest !== "object" || Array.isArray(manifest)) {
    throw new Error(`Expected a manifest mapping: ${directory}`);
  }
  if (Object.hasOwn(manifest, "renderer") || Object.hasOwn(manifest, "peer_dependencies")) throw new Error("Use frontend.entry and package.json peerDependencies; legacy renderer declarations are unsupported");
  const distribution = Object.hasOwn(manifest, "distribution") ? manifest.distribution : "builtin";
  if (distribution !== "builtin" && distribution !== "external") {
    throw new Error(`Invalid plugin distribution in ${directory}: ${distribution}`);
  }
  return { ...manifest, distribution };
}

/** List only host-owned source packages; external source must be installed as a ZIP. */
export async function builtinPluginDirectories(pluginsRoot) {
  const packages = [];
  for (const entry of (await readdir(pluginsRoot, { withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name, "en"))) {
    if (!entry.isDirectory()) continue;
    const directory = join(pluginsRoot, entry.name);
    if (!(await readdir(directory)).includes("manifest.yaml")) continue;
    if ((await readPluginManifest(directory)).distribution === "builtin") packages.push(directory);
  }
  return packages;
}
