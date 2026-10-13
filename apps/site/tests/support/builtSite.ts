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

/** Plain text of an HTML fragment: tags dropped. */
function textOf(html: string) {
  return html.replace(/<[^>]+>/g, "").trim();
}

/**
 * A page's breadcrumb trail (#797): its steps as shown, and the
 * BreadcrumbList structured data inside it. Exactly one trail per page.
 */
export function breadcrumbsOf(html: string) {
  const navs = [...html.matchAll(/<nav class="site-breadcrumbs" aria-label="面包屑">(.*?)<\/nav>/gs)];
  assert.equal(navs.length, 1, "expected exactly one breadcrumb nav");
  const nav = navs[0][1];
  const steps = [...nav.matchAll(/<li class="site-breadcrumbs-item">(.*?)<\/li>/gs)].map(([, item]) => {
    const link = item.match(/^<a href="([^"]+)"[^>]*>(.*)<\/a>$/s);
    if (link) return { label: textOf(link[2]), href: link[1], current: false };
    assert.match(item, /^<span aria-current="page"[^>]*>.*<\/span>$/s, `a breadcrumb step is neither a link nor the current page: ${item}`);
    return { label: textOf(item), href: undefined, current: true };
  });
  const json = nav.match(/<script type="application\/ld\+json">(.*?)<\/script>/s)?.[1];
  assert.ok(json, "the breadcrumb carries no JSON-LD");
  return { steps, jsonLd: JSON.parse(json) as unknown };
}

/** The top bar's first link: the icon and name. */
export function topBarHomeHref(html: string) {
  const bar = html.match(/<header class="site-header"[^>]*>(.*?)<\/header>/s)?.[1];
  assert.ok(bar, "no top bar");
  const first = bar.match(/<a href="([^"]+)"[^>]*>/);
  assert.ok(first, "the top bar has no link");
  return first[1];
}

/**
 * A page's section index (#797) in its two placements: the wide screens'
 * sticky aside and the narrow screens' folded `<details>`, each as its
 * entries (anchor, label without the note, note, nesting level).
 */
export function sectionIndexOf(html: string) {
  const entries = (list: string) =>
    [...list.matchAll(/<li class="site-section-index-item" data-level="(\d)"><a href="#([^"]+)" class="site-section-index-link" data-section-link="([^"]+)">(.*?)<\/a><\/li>/gs)].map(
      ([, level, href, id, content]) => {
        assert.equal(href, id, "an index link's anchor and its data-section-link differ");
        const note = content.match(/<span class="site-section-index-note">(.*?)<\/span>/s)?.[1];
        return { id, label: textOf(content.replace(/<span class="site-section-index-note">.*?<\/span>/s, "")), note, level: Number(level) };
      },
    );
  const aside = html.match(/<nav class="site-section-index site-section-index--aside" aria-label="([^"]+)" data-section-index><p class="site-section-index-title">([^<]+)<\/p>(.*?)<\/nav>/s);
  const inline = html.match(/<details class="site-section-index site-section-index--inline" data-section-index><summary class="site-section-index-summary">([^<]+)<svg.*?<\/summary><nav aria-label="([^"]+)">(.*?)<\/nav><\/details>/s);
  return {
    aside: aside ? { label: aside[1], title: aside[2], entries: entries(aside[3]) } : undefined,
    inline: inline ? { title: inline[1], label: inline[2], entries: entries(inline[3]) } : undefined,
  };
}

/** The `id` of every element of an HTML fragment (only `tag` elements, if given), in order. */
export function idsOf(html: string, tag = "[a-z][a-z0-9-]*") {
  return [...html.matchAll(new RegExp(String.raw`<${tag}\b[^>]*\sid="([^"]+)"`, "g"))].map((match) => match[1]);
}
