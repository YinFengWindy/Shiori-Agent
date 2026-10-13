import type { ShowcaseClipId } from "../../site/src/content/showcase";

/**
 * Length and still moment of each demo clip, by the website's clip id
 * (`SHOWCASE_CLIP_IDS` in apps/site/src/content/showcase.ts is the one list
 * of them; they are also the output file names). `stillSeconds` is the frame
 * the website shows (scripts/stills.ts): one where the feature is fully on
 * screen. Plain data, with no components, so the render scripts can read it
 * in Node; Root.tsx maps each id to its composition.
 */
export const CLIP_TIMING: Record<ShowcaseClipId, { readonly seconds: number; readonly stillSeconds: number }> = {
  // Every message in, the recalled-memory chip beside her reply.
  memory: { seconds: 7.5, stillSeconds: 6.8 },
  // All three gains listed, the stage turned to 朋友.
  affection: { seconds: 6.5, stillSeconds: 6 },
  // Both of her notices in the corner.
  proactive: { seconds: 6.5, stillSeconds: 5.5 },
  // All three channel windows open, her message typed in each.
  channels: { seconds: 6.5, stillSeconds: 5.5 },
  // The tools she used (file, search, shell) stacked by her reply.
  plugins: { seconds: 11, stillSeconds: 2 },
};

/** Every clip shares one frame: 16:10 like the app's screenshots, sharp at the showcase's largest size. */
export const CLIP_FORMAT = { width: 1280, height: 800, fps: 30 } as const;

/**
 * Size budget of every rendered video file (each format), so a clip stays
 * light enough for a phone should a page show it: scripts/render.ts refuses
 * to write past it.
 */
export const CLIP_MAX_BYTES = 1.5 * 1024 * 1024;
