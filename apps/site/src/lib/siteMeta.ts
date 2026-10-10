/**
 * Site-wide identity and outbound links in one data module, so wording or a
 * link change never touches page markup. The canonical origin itself is
 * `site` in astro.config.ts.
 */

/** Product name: the `og:site_name` and the suffix of page titles. */
export const SITE_NAME = "Shiori";

/** Product slogan (also on the README). */
export const SITE_SLOGAN = "让角色走进日常";

/** Closing call of the home page, in 吟风's voice, and the line under it. */
export const DOWNLOAD_HEADLINE = "把我带回家吧，笨蛋。";
export const DOWNLOAD_TAGLINE = "会慢慢喜欢上你的 AI 伴侣";

/** Default meta / OG description for pages that do not set their own. */
export const SITE_DESCRIPTION =
  "Shiori 是以角色为核心的 Personal Agent：记得聊过的往事，会主动找你聊天，也能帮你处理手头的事。";

/** Outbound calls to action. */
export const SITE_LINKS = {
  github: "https://github.com/YinFengWindy/Shiori-Agent",
  releasesLatest: "https://github.com/YinFengWindy/Shiori-Agent/releases/latest",
} as const;

/**
 * `<meta name="theme-color">` value: mirrors `--neutral-50` in the desktop's
 * styles.css, because a `<meta>` cannot read CSS custom properties.
 */
export const SITE_THEME_COLOR = "#fbf9fa";
