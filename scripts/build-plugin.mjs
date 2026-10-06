import { createHash } from "node:crypto";
import { access, mkdir, mkdtemp, readFile, realpath, rm, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";
import { dump } from "js-yaml";
import { readPluginManifest } from "./plugin-distribution.mjs";
import { copyPluginSources, packageFile } from "./plugin-package-files.mjs";
import { buildPluginRenderer } from "./plugin-renderer-build.mjs";
import { zipPluginDirectory } from "./plugin-zip.mjs";

/** Build an independently installable ZIP from one source package, without modifying it. */
export async function buildPlugin({ plugin, output }) {
  const source = await realpath(resolve(plugin));
  const manifest = await readPluginManifest(source);
  if (manifest.distribution !== "external" || manifest.api !== 2 || manifest.package_contract !== 1) {
    throw new Error("ZIP sources require distribution: external, api: 2 and package_contract: 1");
  }
  if (typeof manifest.id !== "string" || !/^[a-z][a-z0-9_-]{0,63}$/.test(manifest.id)) throw new Error("Expected a portable plugin id");
  if (typeof manifest.version !== "string" || !/^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$/.test(manifest.version)) throw new Error("Expected a semantic plugin version");
  if (typeof manifest.runtime_api !== "string" || !manifest.runtime_api.trim()) throw new Error("Expected an explicit runtime_api compatibility range");
  if (!manifest.entry?.startsWith("backend/") || !manifest.entry.endsWith(".py")) throw new Error("Expected a backend/*.py entry");
  packageFile(source, manifest.entry);
  const outputRoot = resolve(output);
  await mkdir(outputRoot, { recursive: true });
  const staging = await mkdtemp(join(outputRoot, ".plugin-build-"));
  try {
    await copyPluginSources(source, staging, manifest);
    await access(packageFile(staging, manifest.entry));
    await buildPluginRenderer(source, staging, manifest);
    await writeFile(join(staging, "manifest.yaml"), dump(manifest, { lineWidth: -1, noRefs: true }), "utf8");
    const archive = join(outputRoot, `${manifest.id}-${manifest.version}.zip`);
    await zipPluginDirectory(staging, archive);
    return { id: manifest.id, version: manifest.version, archive, sha256: createHash("sha256").update(await readFile(archive)).digest("hex") };
  } finally {
    // mkdtemp owns this path; failed builds never delete a source or existing output folder.
    await rm(staging, { recursive: true, force: true });
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { values } = parseArgs({ options: { plugin: { type: "string" }, output: { type: "string", default: "artifacts/plugins" } } });
  if (!values.plugin) throw new Error("Usage: node scripts/build-plugin.mjs --plugin plugins/<id> [--output artifacts/plugins]");
  console.log(JSON.stringify(await buildPlugin({ plugin: values.plugin, output: values.output })));
}
