import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";
import { imageQueriesPlugin } from "./src/lib/imageQueries";

const here = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(here, "..", "..");

/**
 * Shiori public website: fully static output, React only where a component
 * needs it (islands), and the desktop's design tokens compiled by the
 * desktop's own Tailwind theme (postcss.config.mjs, tailwind.config.ts).
 * `site` is the one source of the canonical origin: the layout's canonical /
 * OG URLs, the sitemap and robots.txt are all derived from it.
 */
export default defineConfig({
  site: "https://www.windchant.online",
  output: "static",
  build: {
    // Every page's CSS goes into its HTML: a linked stylesheet in <head>
    // blocks the first paint, which on a slow connection (400 kbps, sharing
    // the line with the first screen's pictures) left the page blank for
    // about 5 s instead of showing the home page loader (#770) at once.
    inlineStylesheets: "always",
  },
  integrations: [react(), sitemap()],
  vite: {
    // `picture.webp?lqip` / `?bytes`: build-time facts for the home page loader.
    plugins: [imageQueriesPlugin()],
    server: {
      fs: {
        // styles.css, the scene backgrounds and the title logo are imported
        // from apps/desktop/renderer, outside this Vite root.
        allow: [repositoryRoot],
      },
    },
  },
});
