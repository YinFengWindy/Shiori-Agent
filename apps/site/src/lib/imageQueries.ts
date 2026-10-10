import { stat } from "node:fs/promises";
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

/** Build-time facts about an image file, by import query. */
const QUERIES = {
  /** A tiny inline placeholder: `lqipDataUri`. */
  lqip: lqipDataUri,
  /** The file's size in bytes (emitted assets are byte-for-byte copies): the loader's progress weights. */
  bytes: async (file: string) => (await stat(file)).size,
} as const;

type QueryName = keyof typeof QUERIES;

const PREFIX = "\0image-query:";

function queryOf(source: string): QueryName | null {
  const query = Object.keys(QUERIES).find((name) => source.endsWith(`?${name}`));
  return (query as QueryName | undefined) ?? null;
}

/**
 * Vite plugin: `import placeholder from "./picture.webp?lqip"` and
 * `import size from "./picture.webp?bytes"` yield those facts about the
 * picture, computed at build time.
 */
export function imageQueriesPlugin(): VitePlugin {
  return {
    name: "shiori-site-image-queries",
    enforce: "pre",
    async resolveId(source, importer) {
      const query = queryOf(source);
      if (!query) return null;
      const resolved = await this.resolve(source.slice(0, -query.length - 1), importer, { skipSelf: true });
      if (!resolved) throw new Error(`cannot resolve ${source}`);
      // The query goes last: Astro's image plugin claims (and tries to read)
      // ids ending in an image extension.
      return `${PREFIX}${resolved.id}:${query}`;
    },
    async load(id) {
      if (!id.startsWith(PREFIX)) return null;
      const separator = id.lastIndexOf(":");
      const file = id.slice(PREFIX.length, separator);
      const query = id.slice(separator + 1) as QueryName;
      this.addWatchFile(file);
      return `export default ${JSON.stringify(await QUERIES[query](file))};`;
    },
  };
}
