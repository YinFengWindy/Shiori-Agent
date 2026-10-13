import { en } from "./en";
import type { Locale } from "./locales";
import { type SiteDictionary, zh } from "./zh";

/*
 * Reading the site's words (#806): a page or component knows its language
 * (a `locale` prop) and takes every word from `siteText(locale)`.
 */

export type { SiteDictionary } from "./zh";

/** Every language's dictionary. */
export const DICTIONARIES: Readonly<Record<Locale, SiteDictionary>> = { zh, en };

/** The words of the site in `locale`. */
export function siteText(locale: Locale): SiteDictionary {
  return DICTIONARIES[locale];
}

/** A page's `<title>` in `locale`: its own name, then the site's (`meta.titleSuffix`). */
export function pageTitle(name: string, locale: Locale): string {
  return `${name} · ${siteText(locale).meta.titleSuffix}`;
}
