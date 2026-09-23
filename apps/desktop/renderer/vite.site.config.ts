import { defineConfig, mergeConfig } from "vite";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import rendererConfig from "./vite.config";

const here = dirname(fileURLToPath(import.meta.url));

/**
 * Build the public static site skeleton with the desktop's existing renderer
 * toolchain (React + Tailwind + the shared design tokens in styles.css),
 * without any of the desktop app's business components, host bridge, or
 * multi-entry (surface/voice/plugin-host) build targets.
 */
export default mergeConfig(rendererConfig, defineConfig({
  root: resolve(here, "../site"),
  publicDir: resolve(here, "public"),
  css: { postcss: here },
  build: {
    outDir: resolve(here, "../site-dist"),
    rollupOptions: { input: resolve(here, "../site/index.html") },
  },
}));
