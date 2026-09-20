import { defineConfig, mergeConfig } from "vite";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";
import rendererConfig from "./vite.config";

const here = dirname(fileURLToPath(import.meta.url));

/** Build the public static entry with the desktop's existing renderer toolchain. */
export default mergeConfig(rendererConfig, defineConfig({
  root: resolve(here, "../showcase"),
  publicDir: resolve(here, "public"),
  css: { postcss: here },
  build: {
    outDir: resolve(here, "../showcase-dist"),
    rollupOptions: { input: resolve(here, "../showcase/index.html") },
  },
}));
