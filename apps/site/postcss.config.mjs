import { fileURLToPath } from "node:url";

/**
 * Compiles the site's CSS (which imports the desktop's styles.css) with the
 * site's Tailwind config: the desktop theme with site-only content globs.
 */
export default {
  plugins: {
    tailwindcss: { config: fileURLToPath(new URL("./tailwind.config.ts", import.meta.url)) },
    autoprefixer: {},
  },
};
