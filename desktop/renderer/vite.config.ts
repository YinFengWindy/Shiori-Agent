import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { defineConfig } from "vite";
import { resolve as resolvePath } from "node:path";
import react from "@vitejs/plugin-react";

const here = dirname(fileURLToPath(import.meta.url));
const desktopRoot = resolve(here, "..");

export default defineConfig({
  root: here,
  base: "./",
  plugins: [react()],
  build: {
    outDir: resolve(desktopRoot, "renderer-dist"),
    emptyOutDir: true,
    rollupOptions: {
      input: {
        main: resolvePath(here, "index.html"),
        pet: resolvePath(here, "pet.html"),
      },
    },
  },
});
