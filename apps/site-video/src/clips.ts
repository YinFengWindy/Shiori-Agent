import type { ShowcaseClipId } from "../../site/src/content/showcase";

/**
 * Length and poster moment of each demo clip, by the website's clip id
 * (`SHOWCASE_CLIP_IDS` in apps/site/src/content/showcase.ts is the one list
 * of them; they are also the output file names). Plain data, with no
 * components, so the render script can read it in Node; Root.tsx maps each
 * id to its composition.
 */
export const CLIP_TIMING: Record<ShowcaseClipId, { readonly seconds: number; readonly posterSeconds: number }> = {
  memory: { seconds: 7.5, posterSeconds: 6.8 },
  affection: { seconds: 6.5, posterSeconds: 6 },
  proactive: { seconds: 6.5, posterSeconds: 5.5 },
  channels: { seconds: 6.5, posterSeconds: 5.5 },
  plugins: { seconds: 11, posterSeconds: 2 },
};

/** Every clip shares one frame: 16:10 like the app's screenshots, sharp at the showcase's largest size. */
export const CLIP_FORMAT = { width: 1280, height: 800, fps: 30 } as const;
