/**
 * Whether the home page plays its loader (#770) on this visit (#797). The
 * loader is a first-impression piece: it holds the narrative still for up
 * to `--site-loader-cap` (10 s) while the first screen downloads, which on
 * a slow line made the browser's Back button feel like it did not work. So
 * it only plays on a plain visit, and is left out when:
 * - the visit is a history step (Back / Forward): the reader is returning
 *   to where they were, and the browser restores that scroll position;
 * - the address carries an anchor (`/#download`, the top bar's icon and
 *   name from another page): the reader asked for a place on the page.
 *
 * Without the loader the first screen's pictures still load (SiteLoader.astro
 * hands them their `src` at once) and the narrative's CGs load as before.
 *
 * Runs inline in the page head, before the first paint, as its own source
 * (`siteLoaderGateScript`): it must stay self-contained, reading nothing but
 * its argument.
 */
export function shouldShowSiteLoader(visit: {
  /** `PerformanceNavigationTiming.type` of this page load, if the browser reports one. */
  navigationType: string | undefined;
  /** `location.hash`: empty, or `#` and the anchor. */
  hash: string;
}): boolean {
  return visit.navigationType !== "back_forward" && visit.hash === "";
}

/** The `<html>` attribute that hides the loader from the first frame (site.css) and tells its script to stand down. */
export const SITE_LOADER_SKIP_ATTRIBUTE = "data-site-loader-skip";

/**
 * The head's inline script: decides with `shouldShowSiteLoader` on this
 * visit and, when the loader stays out, marks `<html>` before anything is
 * painted, so the loader never flashes.
 */
export const siteLoaderGateScript = `if (!(${shouldShowSiteLoader.toString()})({ navigationType: performance.getEntriesByType("navigation")[0]?.type, hash: location.hash })) document.documentElement.setAttribute(${JSON.stringify(SITE_LOADER_SKIP_ATTRIBUTE)}, "");`;
