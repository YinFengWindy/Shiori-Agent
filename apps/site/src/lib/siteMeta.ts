/**
 * Site-wide identity and outbound links in one data module, so wording or a
 * link change never touches page markup. The canonical origin itself is
 * `site` in astro.config.ts.
 */

/** Product name: the `og:site_name` and the suffix of page titles. */
export const SITE_NAME = "Shiori";

/** Product slogan (also on the README). */
export const SITE_SLOGAN = "会慢慢喜欢上你的 AI 伴侣";

/** Closing call of the home page, in 吟风's voice; the slogan sits under it. */
export const DOWNLOAD_HEADLINE = "把我带回家吧，笨蛋。";

/**
 * The home page's description (meta, OG, structured data), and the default
 * for pages that do not set their own. Worded for what people search for a
 * companion app with (AI 伴侣 / AI 女友 / Personal Agent, remembers you, comes to
 * find you, open source and free, Windows), in the slogan's voice (#799).
 */
export const SITE_DESCRIPTION =
  "Shiori 是会慢慢喜欢上你的 AI 伴侣，一款开源免费的 Windows Personal Agent。她可以是你的 AI 女友：记得你们聊过的往事，太久不理她就会主动来找你，也能陪你处理文件、搜索这些手头的事。";

/** The home page's `<title>`: the name, the slogan and the search words it lacks (#799). */
export const HOME_TITLE = `${SITE_NAME} · ${SITE_SLOGAN} · 开源免费的 Personal Agent`;

/**
 * The home page's one `h1` (#799). The download call shows the app icon in
 * its place, so this text is visually hidden: it names the page for search
 * engines and screen readers without touching the design.
 */
export const HOME_HEADING = `${SITE_NAME}：会慢慢喜欢上你的 AI 伴侣，开源的 Personal Agent`;

/** What every other page's `<title>` ends with, after its own name (#799). */
export const SITE_TITLE_SUFFIX = `${SITE_NAME} AI 伴侣`;

/** A page's `<title>`: its own name, then the site's (`SITE_TITLE_SUFFIX`). */
export function pageTitle(name: string): string {
  return `${name} · ${SITE_TITLE_SUFFIX}`;
}

/**
 * `id` of the home page's download call, the narrative's closing state
 * (NarrativeStage.astro): `/#download` opens the home page there.
 */
export const DOWNLOAD_ANCHOR_ID = "download";

/** Outbound calls to action. */
export const SITE_LINKS = {
  /**
   * Home, as the top bar's icon and name and the breadcrumbs' 首页 link it
   * (#797): the narrative's closing download state, not its first line.
   */
  home: `/#${DOWNLOAD_ANCHOR_ID}`,
  github: "https://github.com/YinFengWindy/Shiori-Agent",
  releasesLatest: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest",
  releases: "https://github.com/YinFengWindy/Shiori-Agent/releases",
  license: "https://github.com/YinFengWindy/Shiori-Agent/blob/main/LICENSE",
  /** The top bar's 更新日志: the site's own changelog page, built from the GitHub releases (#792). */
  changelog: "/changelog/",
} as const;

/**
 * `<meta name="theme-color">` value: mirrors `--neutral-50` in the desktop's
 * styles.css, because a `<meta>` cannot read CSS custom properties.
 */
export const SITE_THEME_COLOR = "#fbf9fa";
