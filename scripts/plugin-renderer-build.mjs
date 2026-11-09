import { build } from "esbuild";
import { frontendExports } from "./plugin-frontend.mjs";
import { readFile } from "node:fs/promises";
import { packageFile } from "./plugin-package-files.mjs";
import { pluginRendererAssets } from "./plugin-renderer-assets.mjs";

/** Compile independent ESM entries while preserving the host's SDK/React identities. */
export async function buildPluginRenderer(source, destination, manifest) {
  const exports = await frontendExports(source, manifest);
  if (exports.length) {
    const entry = "renderer/frontend.mjs";
    const result = await build({
      absWorkingDir: source, entryPoints: [packageFile(source, manifest.frontend.entry)],
      outfile: packageFile(destination, entry), bundle: true, format: "esm", platform: "browser", target: "es2022",
      jsx: "automatic", metafile: true,
      plugins: [pluginRendererAssets(destination)],
      external: ["react", "react-dom", "react/*", "react-dom/*", "@yinfengwindy/shiori-sdk"],
      loader: { ".svg": "file", ".png": "file", ".jpg": "file", ".webp": "file", ".woff2": "file" },
      assetNames: "assets/[name]-[hash]",
    });
    const css = Object.values(result.metafile.outputs).some((output) => output.cssBundle) ? ["renderer/frontend.css"] : [];
    const packageJson = JSON.parse(await readFile(packageFile(source, "package.json"), "utf8"));
    const peers = packageJson.peerDependencies;
    const names = ["react", "react-dom", "@yinfengwindy/shiori-sdk"];
    if (!peers || typeof peers !== "object" || names.some((name) => typeof peers[name] !== "string" || !peers[name].trim()) || Object.keys(peers).some((name) => !names.includes(name))) throw new Error("Frontend requires React, React DOM and Shiori SDK peerDependencies in package.json");
    manifest.frontend = { entry, exports, css, peers };
    return;
  }
}
