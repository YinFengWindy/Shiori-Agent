/**
 * The site's background music track — the one place to configure it.
 *
 * `null` means no BGM yet: the sound toggle and BGM volume still work, and
 * nothing is fetched. To enable music, drop a file in `../assets/` and point
 * this at its bundled URL, e.g.
 *
 *   import bgmUrl from "../assets/bgm.mp3";
 *   export const SITE_BGM: string | null = bgmUrl;
 *
 * The track loops and fades in when the visitor turns sound on.
 */
export const SITE_BGM: string | null = null;
