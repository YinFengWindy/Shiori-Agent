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
        voice: resolvePath(here, "voice.html"),
      },
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/@phosphor-icons/")) return "icons-vendor";
          if (id.includes("node_modules/react/") || id.includes("node_modules/react-dom/") || id.includes("node_modules/scheduler/")) return "react-vendor";
          if (id.includes("node_modules/motion/") || id.includes("node_modules/gsap/")) return "motion-vendor";
          return undefined;
        },
      },
    },
  },
});
