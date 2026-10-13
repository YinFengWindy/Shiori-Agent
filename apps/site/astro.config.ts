import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import mdx from "@astrojs/mdx";
import react from "@astrojs/react";
import sitemap from "@astrojs/sitemap";
import { defineConfig } from "astro/config";
import { SITEMAP_I18N, withXDefault } from "./src/i18n/locales";
import { imageBytesPlugin } from "./src/lib/imageQueries";
import { sitemapLastmod } from "./src/lib/pageUpdated";

const here = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(here, "..", "..");
// Each sitemap URL's lastmod is the day its built page states (#799).
const lastmod = sitemapLastmod();

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
  // MDX: the blog posts (src/content/blog, content.config.ts). The lastmod
  // integration comes before the sitemap's, which reads what it notes. The
  // sitemap pairs each page with its other-language version as alternates,
  // plus x-default on the Chinese one, as the pages' heads do (#806).
  integrations: [
    react(),
    mdx(),
    lastmod.integration,
    sitemap({
      i18n: SITEMAP_I18N,
      serialize: async (item) => withXDefault(await lastmod.serialize(item)),
    }),
  ],
  vite: {
    // `picture.webp?bytes`: file sizes for the home page loader's progress.
    plugins: [imageBytesPlugin()],
    server: {
      fs: {
        // styles.css, the scene backgrounds and the title logo are imported
        // from apps/desktop/renderer, outside this Vite root.
        allow: [repositoryRoot],
      },
    },
  },
});
