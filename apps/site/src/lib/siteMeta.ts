import { type Locale, type PageVersions, localePath } from "../i18n/locales";

/**
 * Site-wide identity and outbound links in one data module, so a link change
 * never touches page markup. The canonical origin itself is `site` in
 * astro.config.ts; the words of each language are in the dictionaries
 * (i18n/zh.ts, i18n/en.ts).
 */

/** Product name: the `og:site_name` and the suffix of page titles, the same in every language. */
export const SITE_NAME = "Shiori";

/**
 * `id` of the home page's download call, the narrative's closing state
 * (NarrativeStage.astro): `/#download` opens the home page there.
 */
export const DOWNLOAD_ANCHOR_ID = "download";

/**
 * Home in `locale`, as the top bar's icon and name and the breadcrumbs'
 * first step link it (#797): the narrative's closing download state, not its
 * first line — `/#download`, `/en/#download`.
 */
export function homeDownloadHref(locale: Locale): string {
  return localePath(locale, `/#${DOWNLOAD_ANCHOR_ID}`);
}

/**
 * The site's own sections beside the home page, in the languages they
 * exist in (`PageVersions`): the top bar links each in the page's language,
 * or in Chinese while it has no English version (the English blog and
 * changelog come with #807).
 */
export const SITE_SECTIONS = {
  blog: { zh: "/blog/" },
  /** The site's own changelog page, built from the GitHub releases (#792). */
  changelog: { zh: "/changelog/" },
} as const satisfies Record<string, PageVersions>;

/** Outbound calls to action. */
export const SITE_LINKS = {
  github: "https://github.com/YinFengWindy/Shiori-Agent",
  releasesLatest: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest",
  releases: "https://github.com/YinFengWindy/Shiori-Agent/releases",
  license: "https://github.com/YinFengWindy/Shiori-Agent/blob/main/LICENSE",
} as const;

/**
 * `<meta name="theme-color">` value: mirrors `--neutral-50` in the desktop's
 * styles.css, because a `<meta>` cannot read CSS custom properties.
 */
export const SITE_THEME_COLOR = "#fbf9fa";
