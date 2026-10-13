import { readFile } from "node:fs/promises";
import type { SitemapItem } from "@astrojs/sitemap";
import type { AstroIntegration } from "astro";

/*
 * When a page last changed (#799), stated once in its head and read back
 * into the sitemap's <lastmod>. The page knows its own sources (a post's
 * day, the newest release, the newest post); the sitemap is written after
 * the build from the emitted pages, so it reads the day each page states
 * rather than computing it a second time. Never the build's own clock: the
 * site is rebuilt on every change, and a lastmod moving with every build
 * would tell crawlers every page changed when none did.
 */

/** The `<meta property>` a page states its last change in: Open Graph's `og:updated_time`. */
export const UPDATED_TIME_PROPERTY = "og:updated_time";

const UPDATED_TIME_META = new RegExp(`<meta property="${UPDATED_TIME_PROPERTY}" content="([^"]+)"`);

/** The latest of `dates`; `undefined` when there are none. */
export function latestDate(dates: readonly Date[]): Date | undefined {
  return dates.reduce<Date | undefined>((latest, date) => (latest === undefined || date > latest ? date : latest), undefined);
}

/** The last-change time a built page states (`UPDATED_TIME_PROPERTY`), if it states one. */
export function updatedTimeOf(html: string): string | undefined {
  return html.match(UPDATED_TIME_META)?.[1];
}

/**
 * The sitemap's lastmod, from the built pages: `integration` notes the
 * build's output directory (before @astrojs/sitemap in the integrations, so
 * it is known by the time the sitemap is written), `serialize` is the
 * sitemap's option and gives each URL the time its page states. A page that
 * states none keeps no lastmod.
 */
export function sitemapLastmod() {
  let outDir: URL | undefined;
  const integration: AstroIntegration = {
    name: "shiori-sitemap-lastmod",
    hooks: {
      "astro:config:done": ({ config }) => {
        outDir = config.outDir;
      },
    },
  };
  async function serialize(item: SitemapItem): Promise<SitemapItem> {
    if (!outDir) throw new Error("the sitemap lastmod integration must be registered: the output directory is unknown");
    const { pathname } = new URL(item.url);
    const page = new URL(`.${pathname}${pathname.endsWith("/") ? "index.html" : ""}`, outDir);
    const updated = updatedTimeOf(await readFile(page, "utf8"));
    return updated === undefined ? item : { ...item, lastmod: updated };
  }
  return { integration, serialize };
}
