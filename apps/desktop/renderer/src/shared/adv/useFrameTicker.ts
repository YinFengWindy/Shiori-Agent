import { useEffect, useEffectEvent } from "react";

/** A frame gap longer than this (tab in background, debugger) counts as this much. */
const MAX_FRAME_MS = 250;

/**
 * Call `onTick(elapsedMs)` every animation frame while `active` is true.
 * The latest `onTick` is always used without restarting the loop.
 */
export function useFrameTicker(active: boolean, onTick: (elapsedMs: number) => void) {
  const handleTick = useEffectEvent(onTick);

  useEffect(() => {
    if (!active) return;
    let frame = 0;
    let last: number | null = null;
    function loop(now: number) {
      if (last !== null) handleTick(Math.min(now - last, MAX_FRAME_MS));
      last = now;
      frame = requestAnimationFrame(loop);
    }
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, [active]);
}
