import { build } from "esbuild";
import { packageFile } from "./plugin-package-files.mjs";

/** Read named contributions without evaluating plugin code or following imports. */
export async function frontendExports(directory, manifest) {
  if (!manifest.frontend) return [];
  const result = await build({ entryPoints: [packageFile(directory, manifest.frontend.entry)], write: false, bundle: false, format: "esm", jsx: "automatic", metafile: true, logLevel: "silent" });
  const names = Object.values(result.metafile.outputs)[0].exports;
  if (!names.length || names.some((name) => !["ui", "background", "surface"].includes(name))) throw new Error("Frontend must explicitly export ui, background or surface");
  return names;
}
