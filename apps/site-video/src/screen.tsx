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

/** The app's ease-out (`--ease-out-soft` in the desktop's styles.css). */
export const easeOutSoft = Easing.bezier(0.23, 1, 0.32, 1);

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
