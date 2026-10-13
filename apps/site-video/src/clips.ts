/**
 * The demo clips: ids (also the output file names), length and poster
 * moment. Plain data, with no components, so the render script can read it
 * in Node; Root.tsx maps each id to its composition.
 */
export const DEMO_CLIPS = [
  { id: "memory", seconds: 7.5, posterSeconds: 6.8 },
  { id: "affection", seconds: 6.5, posterSeconds: 6 },
  { id: "proactive", seconds: 6.5, posterSeconds: 5.5 },
  { id: "channels", seconds: 6.5, posterSeconds: 5.5 },
  { id: "plugins", seconds: 11, posterSeconds: 2 },
] as const;

/** A demo clip's id. */
export type DemoClipId = (typeof DEMO_CLIPS)[number]["id"];

/** Every clip shares one frame: 16:10 like the app's screenshots, sharp at the showcase's largest size. */
export const CLIP_FORMAT = { width: 1280, height: 800, fps: 30 } as const;
