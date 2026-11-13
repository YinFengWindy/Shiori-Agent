/**
 * Locates the third-party packages the desktop unit test processes special-case
 * (see `test-unit-loader.mjs` and `test-unit-prebundle.mjs`), and the files
 * Node's ESM resolver picks inside them.
 *
 * Everything is resolved from the plugin SDK package, which owns the Base UI
 * and happy-dom copies the renderer, plugins and the DOM harness load, so a
 * second copy elsewhere in the tree is never mistaken for them.
 */
import { readFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

/** The conditions Node's ESM resolver matches against `exports` for an `import`. */
const esmConditions = new Set(["node", "import", "module-sync", "default"]);

/** Returns a `require` rooted at the plugin SDK's `package.json`. */
export async function sdkPackageRequire() {
  // The main entry is `src/index.ts`, one level below the package root.
  const sdkManifestPath = join(dirname(fileURLToPath(import.meta.resolve("@yinfengwindy/shiori-sdk"))), "..", "package.json");
  if (JSON.parse(await readFile(sdkManifestPath, "utf8")).name !== "@yinfengwindy/shiori-sdk") {
    throw new Error(`test-unit-packages: ${sdkManifestPath} is not the plugin SDK manifest; the SDK main entry moved, update sdkPackageRequire().`);
  }
  return createRequire(sdkManifestPath);
}

/** Reads the `package.json` at `manifestPath`. */
export async function readPackageManifest(manifestPath) {
  return JSON.parse(await readFile(manifestPath, "utf8"));
}

/**
 * The file an `import` of `subpath` (`"."` or `"./x"`) resolves to inside the
 * package whose manifest is `manifest`, as a path relative to the package
 * root; `undefined` when the package exposes no ESM target for it.
 *
 * Follows `exports` in key order like Node does, and falls back to `main` for
 * a package without `exports`.
 */
export function esmEntryTarget(manifest, subpath) {
  if (manifest.exports === undefined) return subpath === "." ? (manifest.main ?? "index.js") : undefined;
  const exportsMap = typeof manifest.exports === "string" || Object.keys(manifest.exports).every((key) => !key.startsWith("."))
    ? { ".": manifest.exports }
    : manifest.exports;
  return conditionalTarget(exportsMap[subpath]);
}

function conditionalTarget(entry) {
  if (typeof entry === "string") return entry;
  if (!entry || typeof entry !== "object" || Array.isArray(entry)) return undefined;
  for (const [condition, value] of Object.entries(entry)) {
    if (!esmConditions.has(condition)) continue;
    const target = conditionalTarget(value);
    if (target !== undefined) return target;
  }
  return undefined;
}
