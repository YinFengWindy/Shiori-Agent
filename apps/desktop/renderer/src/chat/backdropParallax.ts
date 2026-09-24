/**
 * Pointer parallax for the chat background: the portrait drifts up to 12px
 * away from the cursor while the conversation drifts 3px toward it. The
 * offset eases toward its target with a frame-rate independent lerp, and the
 * loop stops the moment it settles, so a still pointer costs no frames.
 */

/** Largest background shift, px (the backdrop layer bleeds this far past its frame). */
export const parallaxBackdropMaxPx = 12;
/** Largest conversation shift, px, the other way. */
export const parallaxForegroundMaxPx = 3;

/** Share of the remaining distance covered per 60 Hz frame. */
const lerpPerFrame = 0.075;
/** Closer than this (in normalised units, ≈0.24px on the background) snaps to the target. */
const settleEpsilon = 0.02;
/** Longest step considered, so a stalled tab does not jump. */
const maxStepMs = 64;
const frameMs = 1000 / 60;

/** A normalised pointer position: -1…1 on each axis, 0 at the centre. */
export type ParallaxPoint = { readonly x: number; readonly y: number };

export const parallaxCentre: ParallaxPoint = { x: 0, y: 0 };

function clampUnit(value: number): number {
  return Math.max(-1, Math.min(1, value));
}

/** Where the pointer sits inside `rect`, normalised to -1…1. */
export function parallaxTarget(clientX: number, clientY: number, rect: Pick<DOMRect, "left" | "top" | "width" | "height">): ParallaxPoint {
  if (rect.width <= 0 || rect.height <= 0) return parallaxCentre;
  return {
    x: clampUnit(((clientX - rect.left) / rect.width - 0.5) * 2),
    y: clampUnit(((clientY - rect.top) / rect.height - 0.5) * 2),
  };
}

/** Moves `current` toward `target` for a frame of `dtMs`; snaps and reports `settled` once close enough. */
export function stepParallax(current: ParallaxPoint, target: ParallaxPoint, dtMs: number): { point: ParallaxPoint; settled: boolean } {
  const dt = Math.min(maxStepMs, Math.max(0, dtMs));
  const factor = 1 - Math.pow(1 - lerpPerFrame, dt / frameMs);
  const x = current.x + (target.x - current.x) * factor;
  const y = current.y + (target.y - current.y) * factor;
  if (Math.abs(target.x - x) < settleEpsilon && Math.abs(target.y - y) < settleEpsilon) {
    return { point: target, settled: true };
  }
  return { point: { x, y }, settled: false };
}

/** The CSS transforms for a point; empty at the centre so settled layers carry no transform. */
export function parallaxTransforms(point: ParallaxPoint): { backdrop: string; foreground: string } {
  if (point.x === 0 && point.y === 0) return { backdrop: "", foreground: "" };
  const px = (value: number) => `${value.toFixed(2)}px`;
  return {
    backdrop: `translate3d(${px(-point.x * parallaxBackdropMaxPx)}, ${px(-point.y * parallaxBackdropMaxPx)}, 0)`,
    foreground: `translate3d(${px(point.x * parallaxForegroundMaxPx)}, ${px(point.y * parallaxForegroundMaxPx)}, 0)`,
  };
}

type ParallaxLoopOptions = {
  /** Draws a point (writes the transforms). */
  apply: (point: ParallaxPoint) => void;
  requestFrame?: (callback: FrameRequestCallback) => number;
  cancelFrame?: (handle: number) => void;
};

/**
 * The animation loop: `setTarget` starts frames if none are running, each
 * frame steps toward the target, and the loop ends once settled. `reset`
 * stops at once and draws the centre.
 */
export function createParallaxLoop({ apply, requestFrame = requestAnimationFrame, cancelFrame = cancelAnimationFrame }: ParallaxLoopOptions) {
  let current = parallaxCentre;
  let target = parallaxCentre;
  let handle = 0;
  let lastTime = 0;

  const tick = (now: number) => {
    const step = stepParallax(current, target, lastTime ? now - lastTime : frameMs);
    lastTime = now;
    current = step.point;
    apply(current);
    handle = step.settled ? 0 : requestFrame(tick);
  };

  return {
    setTarget(next: ParallaxPoint) {
      target = next;
      if (handle) return;
      lastTime = 0;
      handle = requestFrame(tick);
    },
    reset() {
      if (handle) cancelFrame(handle);
      handle = 0;
      current = parallaxCentre;
      target = parallaxCentre;
      apply(current);
    },
    /** Whether frames are currently scheduled. */
    get running() {
      return handle !== 0;
    },
    get point() {
      return current;
    },
  };
}
