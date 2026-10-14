/**
 * The showcase's features, in page order: the one list of their ids. Each
 * has a still, a screenshot of the real desktop app captured by
 * `scripts/stills.ts` (`pnpm run site:stills`) into
 * `assets/showcase/<id>.webp`, which `lib/siteAssets.ts` picks up by the
 * same ids.
 */
export const SHOWCASE_CLIP_IDS = ["memory", "affection", "proactive", "channels", "plugins"] as const;

/** A demo clip of the showcase. */
export type ShowcaseClipId = (typeof SHOWCASE_CLIP_IDS)[number];

/**
 * Size budget of every showcase still, so the showcase stays light on a slow
 * line: the stills script refuses to write past it and the build test checks
 * the emitted files against it.
 */
export const SHOWCASE_STILL_MAX_BYTES = 150 * 1024;

/**
 * The words of one feature block of the home page showcase (#772), in each
 * dictionary (i18n/zh.ts, i18n/en.ts) by the feature id. Every claim must
 * match README.md; titles stay a few words and lines one sentence, so a
 * block reads at a glance on a phone.
 */
export interface ShowcaseFeatureCopy {
  /** Short title, in the story type. */
  readonly title: string;
  /** One short line under the title. */
  readonly line: string;
  /** What the still shows, as its alt text. */
  readonly stillAlt: string;
}
