import { build } from "esbuild";
import { existsSync } from "node:fs";
import { PLUGIN_RENDERER_SOURCES } from "./plugin-distribution.mjs";
import { copyPackagePath, packageFile } from "./plugin-package-files.mjs";

/** Compile independent ESM entries while preserving the host's SDK/React identities. */
export async function buildPluginRenderer(source, destination, manifest) {
  const targets = new Set();
  for (const [kind, declaration] of Object.entries(manifest.renderer ?? {})) {
    if (!Object.hasOwn(PLUGIN_RENDERER_SOURCES, kind)) throw new Error(`Unknown renderer kind: ${kind}`);
    const output = packageFile(destination, declaration.entry);
    if (!declaration.entry.endsWith(".mjs") || targets.has(output)) throw new Error(`Expected unique .mjs entry: ${declaration.entry}`);
    targets.add(output);
    const result = await build({
      absWorkingDir: source,
      entryPoints: [packageFile(source, PLUGIN_RENDERER_SOURCES[kind])],
      outfile: output,
      bundle: true, format: "esm", platform: "browser", target: "es2022",
      jsx: "automatic", metafile: true,
      external: ["react", "react-dom", "react/*", "react-dom/*", "@yinfengwindy/shiori-sdk"],
      loader: { ".svg": "file", ".png": "file", ".jpg": "file", ".webp": "file", ".woff2": "file" },
      assetNames: "assets/[name]-[hash]",
    });
    const css = declaration.css;
    if (!Array.isArray(css)) throw new Error(`renderer.${kind}.css must be an array`);
    const emittedCss = declaration.entry.replace(/\.mjs$/, ".css");
    if (Object.values(result.metafile.outputs).some((entry) => entry.cssBundle) && !css.includes(emittedCss)) {
      throw new Error(`Declare generated stylesheet in renderer.${kind}.css: ${emittedCss}`);
    }
    for (const name of css) {
      const path = packageFile(destination, name);
      if (!existsSync(path)) await copyPackagePath(source, destination, name);
    }
  }
}
