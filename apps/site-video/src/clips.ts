import type { ShowcaseClipId } from "../../site/src/content/showcase";

/**
 * Length of each demo clip, by the website's clip id (`SHOWCASE_CLIP_IDS` in
 * apps/site/src/content/showcase.ts is the one list of them; they are also
 * the output file names). Plain data, with no components, so the render
 * script can read it in Node; Root.tsx maps each id to its composition.
 */
export const CLIP_TIMING: Record<ShowcaseClipId, { readonly seconds: number }> = {
  memory: { seconds: 7.5 },
  affection: { seconds: 6.5 },
  proactive: { seconds: 6.5 },
  channels: { seconds: 6.5 },
  plugins: { seconds: 11 },
};

/** Every clip shares one frame: 16:10 like the app's screenshots, sharp at the showcase's largest size. */
export const CLIP_FORMAT = { width: 1280, height: 800, fps: 30 } as const;

/**
 * Size budget of every rendered video file (each format), so a clip stays
 * light enough for a phone should a page show it: scripts/render.ts refuses
 * to write past it.
 */
export const CLIP_MAX_BYTES = 1.5 * 1024 * 1024;
