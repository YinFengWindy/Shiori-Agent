import type { AstroUserConfig } from "astro";
import sharp from "sharp";

/** Vite's `Plugin`, through Astro's config type: the site does not depend on Vite directly. */
type VitePlugin = Extract<NonNullable<NonNullable<AstroUserConfig["vite"]>["plugins"]>[number], { name: string }>;

/** Width of a placeholder in pixels: enough for a silhouette once CSS blurs it, small enough to inline. */
export const LQIP_WIDTH = 20;

/**
 * A tiny WebP of `file` (alpha kept) as a `data:` URI, for inlining into the
 * HTML so a blurred stand-in paints with the first frame (the home page
 * loader, #770).
 */
export async function lqipDataUri(file: string, width = LQIP_WIDTH): Promise<string> {
  const webp = await sharp(file).resize({ width }).webp({ quality: 60, alphaQuality: 60, effort: 6 }).toBuffer();
  return `data:image/webp;base64,${webp.toString("base64")}`;
}

const QUERY = "?lqip";
const PREFIX = "\0lqip:";
// No image extension at the end of the virtual id: Astro's image plugin
// claims (and tries to read) ids ending in `.webp`.
const SUFFIX = ".lqip";

/**
 * Vite plugin: `import placeholder from "./picture.webp?lqip"` yields
 * `lqipDataUri` of that picture, computed at build time.
 */
export function lqipPlugin(): VitePlugin {
  return {
    name: "shiori-site-lqip",
    enforce: "pre",
    async resolveId(source, importer) {
      if (!source.endsWith(QUERY)) return null;
      const resolved = await this.resolve(source.slice(0, -QUERY.length), importer, { skipSelf: true });
      if (!resolved) throw new Error(`cannot resolve ${source} for a placeholder`);
      return `${PREFIX}${resolved.id}${SUFFIX}`;
    },
    async load(id) {
      if (!id.startsWith(PREFIX) || !id.endsWith(SUFFIX)) return null;
      const file = id.slice(PREFIX.length, -SUFFIX.length);
      this.addWatchFile(file);
      return `export default ${JSON.stringify(await lqipDataUri(file))};`;
    },
  };
}
