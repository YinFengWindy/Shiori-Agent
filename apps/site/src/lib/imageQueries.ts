import { stat } from "node:fs/promises";
import type { AstroUserConfig } from "astro";

/** Vite's `Plugin`, through Astro's config type: the site does not depend on Vite directly. */
type VitePlugin = Extract<NonNullable<NonNullable<AstroUserConfig["vite"]>["plugins"]>[number], { name: string }>;

const QUERY = "?bytes";
const PREFIX = "\0image-bytes:";
// No image extension at the end of the virtual id: Astro's image plugin
// claims (and tries to read) ids ending in `.webp`.
const SUFFIX = ":bytes";

/**
 * Vite plugin: `import size from "./picture.webp?bytes"` yields the file's
 * size in bytes, read at build time (emitted assets are byte-for-byte
 * copies). The home page loader weighs its progress bar by these sizes.
 */
export function imageBytesPlugin(): VitePlugin {
  return {
    name: "shiori-site-image-bytes",
    enforce: "pre",
    async resolveId(source, importer) {
      if (!source.endsWith(QUERY)) return null;
      const resolved = await this.resolve(source.slice(0, -QUERY.length), importer, { skipSelf: true });
      if (!resolved) throw new Error(`cannot resolve ${source}`);
      return `${PREFIX}${resolved.id}${SUFFIX}`;
    },
    async load(id) {
      if (!id.startsWith(PREFIX)) return null;
      const file = id.slice(PREFIX.length, -SUFFIX.length);
      this.addWatchFile(file);
      return `export default ${(await stat(file)).size};`;
    },
  };
}
