import type { CSSProperties, ReactNode } from "react";
import { AbsoluteFill, Easing, Img, interpolate, useCurrentFrame, useVideoConfig } from "remotion";

/** Size of every app screenshot under assets/readme: the coordinate space the clips place things in. */
export const SCREEN_WIDTH = 1440;
export const SCREEN_HEIGHT = 900;

/** A rectangle on a screenshot, in screenshot pixels. */
export interface Rect {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

/**
 * A `cubic-bezier()` motion token of the desktop's tokens.css (loaded by
 * Root.tsx) as a Remotion easing, read from the page once it is first used.
 */
function easingToken(name: string) {
  let easing: ((t: number) => number) | undefined;
  return (t: number) => {
    if (!easing) {
      const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
      const points = /^cubic-bezier\(([^)]+)\)$/.exec(value)?.[1]?.split(",").map(Number);
      if (!points || points.length !== 4 || points.some(Number.isNaN)) {
        throw new Error(`${name} is not a cubic-bezier() token: "${value}"`);
      }
      const [x1 = 0, y1 = 0, x2 = 0, y2 = 0] = points;
      easing = Easing.bezier(x1, y1, x2, y2);
    }
    return easing(t);
  };
}

/** The app's ease-out, `--ease-out-soft`. */
export const easeOutSoft = easingToken("--ease-out-soft");

/** 0 → 1 over `duration` frames from `start`, eased out; clamped on both ends. */
export function progress(frame: number, start: number, duration: number) {
  return interpolate(frame, [start, start + duration], [0, 1], {
    easing: easeOutSoft,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

/** Seconds → frames at the composition's frame rate. */
export function useSeconds() {
  const { fps } = useVideoConfig();
  return (seconds: number) => Math.round(seconds * fps);
}

/**
 * A 1440×900 stage scaled to fill the composition, with a slow push-in
 * across the clip. Children are laid out in screenshot pixels.
 */
export function Screen({ children, zoom = 0.04, origin = "50% 50%" }: { children: ReactNode; zoom?: number; origin?: string }) {
  const frame = useCurrentFrame();
  const { width, durationInFrames } = useVideoConfig();
  const push = interpolate(frame, [0, durationInFrames], [1, 1 + zoom]);
  return (
    <AbsoluteFill style={{ overflow: "hidden" }}>
      <div
        style={{
          position: "absolute",
          width: SCREEN_WIDTH,
          height: SCREEN_HEIGHT,
          transformOrigin: "0 0",
          transform: `scale(${width / SCREEN_WIDTH})`,
        }}
      >
        <div style={{ position: "absolute", inset: 0, transformOrigin: origin, transform: `scale(${push})` }}>{children}</div>
      </div>
    </AbsoluteFill>
  );
}

/** The whole screenshot as the stage's base layer. */
export function Shot({ src, style }: { src: string; style?: CSSProperties }) {
  return <Img src={src} style={{ position: "absolute", inset: 0, width: SCREEN_WIDTH, height: SCREEN_HEIGHT, ...style }} />;
}

/** One region of the screenshot, cut out in place (for revealing it on its own). */
export function ShotRegion({ src, rect, style }: { src: string; rect: Rect; style?: CSSProperties }) {
  return (
    <div style={{ position: "absolute", left: rect.x, top: rect.y, width: rect.w, height: rect.h, overflow: "hidden", ...style }}>
      <Img src={src} style={{ position: "absolute", left: -rect.x, top: -rect.y, width: SCREEN_WIDTH, height: SCREEN_HEIGHT }} />
    </div>
  );
}
