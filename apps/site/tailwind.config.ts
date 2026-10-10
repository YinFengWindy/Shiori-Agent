import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import type { Config } from "tailwindcss";
import desktopConfig from "../desktop/renderer/tailwind.config";

const here = dirname(fileURLToPath(import.meta.url));

/**
 * The desktop renderer's Tailwind theme (semantic colors, type scale, radii,
 * shadows, motion tokens), reused as-is so the site and the app share one
 * design system. Only `content` differs: the site scans its own sources and
 * the shared class-name modules it imports (SDK and desktop `shared/styles.ts`),
 * not the whole desktop renderer, so desktop-only classes stay out of the site's CSS.
 */
export default {
  ...desktopConfig,
  content: [
    resolve(here, "src/**/*.{astro,ts,tsx}"),
    resolve(here, "../../packages/sdk/src/styles.ts"),
    resolve(here, "../desktop/renderer/src/shared/styles.ts"),
  ],
} satisfies Config;
