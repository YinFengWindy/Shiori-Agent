import type { SitemapItem } from "@astrojs/sitemap";

/*
 * The site's languages (#805, #806): Chinese at the root, English under
 * `/en/`. Pure data and path helpers, with no Astro import, so the config
 * (astro.config.ts, the sitemap's alternates) and the unit tests read them
 * too. The words themselves are in the dictionaries (`./zh.ts`, `./en.ts`).
 * Nothing redirects by the browser's language: a visitor only ever changes
 * language by a link (the language switch, the English prompt).
 */

/** The site's languages, the default (root) one first. */
export const LOCALES = ["zh", "en"] as const;

/** One of the site's languages. */
export type Locale = (typeof LOCALES)[number];

/** The root language: its pages have no path prefix, and it is the `x-default` alternate. */
export const DEFAULT_LOCALE = "zh" satisfies Locale;

/** How a language is named to browsers, crawlers and link previews. */
export interface LocaleInfo {
  /** `<html lang>` and JSON-LD `inLanguage`. */
  readonly htmlLang: string;
  /** `hreflang` of the page's alternate links (head and sitemap). */
  readonly hreflang: string;
  /** Open Graph `og:locale`. */
  readonly ogLocale: string;
  /** Path prefix of its pages: empty for the root language, `/en` for English. */
  readonly prefix: string;
  /**
   * Whether its pages offer the English site, once, to a visitor whose
   * browser reads no Chinese (lib/languagePrompt.ts): the Chinese pages do.
   */
  readonly offersEnglish: boolean;
}

export const LOCALE_INFO: Readonly<Record<Locale, LocaleInfo>> = {
  zh: { htmlLang: "zh-CN", hreflang: "zh-CN", ogLocale: "zh_CN", prefix: "", offersEnglish: true },
  en: { htmlLang: "en", hreflang: "en", ogLocale: "en_US", prefix: "/en", offersEnglish: false },
};

/** `hreflang` of the alternate a visitor whose language the site lacks gets: the Chinese page. */
export const X_DEFAULT_HREFLANG = "x-default";

/** The site path of `path` (a root-relative path, `/` included) in `locale`: `/` → `/en/`. */
export function localePath(locale: Locale, path: string): string {
  if (!path.startsWith("/")) throw new Error(`a site path starts with "/", got ${path}`);
  return `${LOCALE_INFO[locale].prefix}${path}`;
}

/** The home page of `locale`. */
export function localeHome(locale: Locale): string {
  return localePath(locale, "/");
}

/** The language a page is not in, which the language switch leads to. */
export function otherLocale(locale: Locale): Locale {
  return locale === "zh" ? "en" : "zh";
}

/**
 * One page in the languages it exists in: its site path in each. A page
 * written in one language only (a post without an English version, #807)
 * names that one, so no alternate is claimed for it.
 */
export type PageVersions = Readonly<Partial<Record<Locale, string>>>;

/**
 * Where `versions` sends a visitor reading in `locale`: the page in that
 * language, or else in the root language (a section the other language does
 * not have yet, such as the English blog before #807).
 */
export function versionFor(locale: Locale, versions: PageVersions): string {
  const path = versions[locale] ?? versions[DEFAULT_LOCALE];
  if (path === undefined) throw new Error(`a page needs its ${DEFAULT_LOCALE} version`);
  return path;
}

/**
 * The language switch's target on a page in `locale`: the same page in the
 * other language, or that language's home page when the page has no version
 * in it.
 */
export function languageSwitchHref(locale: Locale, versions: PageVersions): string {
  const other = otherLocale(locale);
  return versions[other] ?? localeHome(other);
}

/** One `<link rel="alternate" hreflang>` of a page. */
export interface HreflangLink {
  readonly hreflang: string;
  readonly href: string;
}

/**
 * The hreflang alternates of a page, absolute on `site`: one per language it
 * exists in, itself included, then `x-default` pointing at the Chinese
 * version. None for a page in one language only: there is nothing to pair.
 */
export function hreflangLinks(versions: PageVersions, site: URL): HreflangLink[] {
  const present = LOCALES.flatMap((locale) => {
    const path = versions[locale];
    return path === undefined ? [] : [{ hreflang: LOCALE_INFO[locale].hreflang, href: new URL(path, site).href }];
  });
  if (present.length < 2) return [];
  const fallback = versions[DEFAULT_LOCALE];
  if (fallback === undefined) throw new Error(`a page in several languages needs its ${DEFAULT_LOCALE} version for x-default`);
  return [...present, { hreflang: X_DEFAULT_HREFLANG, href: new URL(fallback, site).href }];
}

/**
 * @astrojs/sitemap's `i18n` option: it pairs every page with the pages of
 * the same path in the other language (`/` with `/en/`) as `xhtml:link`
 * alternates, and pairs nothing for a page in one language only.
 */
export const SITEMAP_I18N = {
  defaultLocale: DEFAULT_LOCALE,
  locales: Object.fromEntries(LOCALES.map((locale) => [locale, LOCALE_INFO[locale].hreflang])),
};

/**
 * A sitemap entry with the `x-default` alternate added to the language pair
 * the sitemap found for it (`SITEMAP_I18N`), the same as the page's head
 * (`hreflangLinks`): the Chinese page. Entries without alternates stay as they are.
 */
export function withXDefault(item: SitemapItem): SitemapItem {
  const links = item.links;
  if (!links || links.length < 2) return item;
  const fallback = links.find((link) => link.lang === LOCALE_INFO[DEFAULT_LOCALE].hreflang);
  if (!fallback) throw new Error(`sitemap alternates of ${item.url} lack the ${DEFAULT_LOCALE} page`);
  return { ...item, links: [...links, { url: fallback.url, lang: X_DEFAULT_HREFLANG }] };
}
