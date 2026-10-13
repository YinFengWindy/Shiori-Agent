import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/*
 * Reading the built site (the package's `test` script runs `astro build`
 * into dist/, and `astro build --mode drafts` into dist-drafts/, first).
 * Reading the emitted files directly is what a crawler that does not
 * execute JavaScript sees.
 */

const siteRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

/** The production origin (`site` in astro.config.ts). */
export const ORIGIN = "https://www.windchant.online";

/** One build's output directory. */
export interface BuiltSite {
  readonly dir: string;
  /** The text of an emitted file, by its path in the output. */
  read(path: string): string;
  /** Whether the build emitted `path`. */
  has(path: string): boolean;
}

function builtSite(dirName: string, command: string): BuiltSite {
  const dir = resolve(siteRoot, dirName);
  return {
    dir,
    has: (path) => existsSync(resolve(dir, path)),
    read(path) {
      const file = resolve(dir, path);
      assert.ok(existsSync(file), `expected ${path} in ${dirName}/; run \`${command}\` first`);
      return readFileSync(file, "utf8");
    },
  };
}

/** The production build: drafts left out. */
export const dist = builtSite("dist", "astro build");

/** The drafts-mode build: drafts listed like published posts. */
export const draftsDist = builtSite("dist-drafts", "astro build --mode drafts --outDir dist-drafts");

/** The `content` of the one `<meta>` whose `attribute` equals `key`. */
export function metaContent(html: string, attribute: "name" | "property", key: string) {
  const matches = [...html.matchAll(new RegExp(`<meta ${attribute}="${key}" content="([^"]*)"`, "g"))];
  assert.equal(matches.length, 1, `expected exactly one <meta ${attribute}="${key}">`);
  return matches[0][1];
}

/** The output file behind an absolute URL on the site origin. */
export function distPathOf(url: string) {
  assert.ok(url.startsWith(`${ORIGIN}/`), `${url} must be on ${ORIGIN}`);
  const path = url.slice(ORIGIN.length + 1);
  return path === "" || path.endsWith("/") ? `${path}index.html` : path;
}

/** Every page URL the build's sitemap lists. */
export function sitemapPages(site: BuiltSite) {
  const index = site.read("sitemap-index.xml");
  const sitemaps = [...index.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
  assert.ok(sitemaps.length > 0, "sitemap index lists no sitemaps");
  return sitemaps.flatMap((url) => [...site.read(distPathOf(url)).matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]));
}
