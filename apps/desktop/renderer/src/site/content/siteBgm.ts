import bgmUrl from "../assets/bgm.mp3";

/**
 * The site's background music track — the one place to configure it.
 *
 * 「Sweet Everyday Moments」, owner-generated, cut at 2:43 (before the
 * trailing silence) so the loop restarts without a gap, and stripped of
 * metadata. Set this to `null` to go back to no BGM: the sound toggle and
 * BGM volume still work, and nothing is fetched.
 *
 * The track loops and fades in when the visitor turns sound on.
 */
export const SITE_BGM: string | null = bgmUrl;
