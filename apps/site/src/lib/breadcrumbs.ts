/**
 * The reading pages' breadcrumb trail (#797): 首页 / 博客 / a post, 首页 /
 * 更新日志. Pure data and its BreadcrumbList structured data.
 */

import { siteText } from "../i18n";
import type { Locale } from "../i18n/locales";
import { homeDownloadHref } from "./siteMeta";

/** One step of a trail: a page and the link to it. */
export interface Crumb {
  label: string;
  /** Path on the site; the last crumb is the page itself. */
  href: string;
}

/**
 * The trail's first step in `locale`. It links to the home page's closing
 * download state, the same place as the top bar's icon and name.
 */
export function homeCrumb(locale: Locale): Crumb {
  return { label: siteText(locale).breadcrumbs.home, href: homeDownloadHref(locale) };
}

/**
 * schema.org BreadcrumbList for a trail, URLs absolute on `site`. An item
 * names the page itself: an in-page anchor (the home crumb's `#download`) is
 * not part of the page's URL, so it is left out.
 */
export function breadcrumbListJsonLd(trail: readonly Crumb[], site: URL) {
  if (trail.length === 0) throw new Error("a breadcrumb trail needs at least one step");
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((crumb, index) => {
      const url = new URL(crumb.href, site);
      url.hash = "";
      return { "@type": "ListItem", position: index + 1, name: crumb.label, item: url.href };
    }),
  };
}
