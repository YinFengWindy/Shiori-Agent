import { build } from "esbuild";
import { copyFile, mkdir } from "node:fs/promises";

await mkdir("package/backend", { recursive: true });
await mkdir("package/assets", { recursive: true });
await copyFile("manifest.yaml", "package/manifest.yaml");
await copyFile("src/plugin.py", "package/backend/plugin.py");
await copyFile("src/label.txt", "package/assets/label.txt");
await copyFile("src/style.css", "package/style.css");
await build({
  entryPoints: ["src/ui.tsx", "src/background.ts", "src/surface.tsx"],
  outdir: "package/renderer",
  outExtension: { ".js": ".mjs" },
  bundle: true,
  format: "esm",
  platform: "browser",
  target: "es2022",
  external: ["react", "react-dom", "react/*", "react-dom/*"],
});
