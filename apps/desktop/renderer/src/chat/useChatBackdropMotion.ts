import { useEffect, useRef, type RefObject } from "react";
import { useReducedMotion } from "motion/react";
import { useAppearancePrefs } from "../shared/useAppearancePrefs";
import { createParallaxLoop, parallaxTarget, parallaxTransforms } from "./backdropParallax";

type UseChatBackdropMotionArgs = {
  /** Receives the pointer (the chat column). */
  surfaceRef: RefObject<HTMLElement | null>;
  /** The conversation layer that drifts slightly toward the pointer. */
  foregroundRef: RefObject<HTMLElement | null>;
  /** A background portrait is shown. */
  hasBackdrop: boolean;
  /** The window is visible and focused. */
  windowActive: boolean;
};

/**
 * The chat background's ambient motion (设置 › 外观 › 背景呼吸与视差, on by
 * default): a very slow breathing scale (CSS, `.chat-backdrop-breathe`) and
 * pointer parallax. Both stop under reduced motion; while the window is
 * hidden or blurred the breathing pauses and the parallax returns to centre.
 * Returns the ref for the parallax layer and the breathing state for
 * `ChatSurfaceBackdrop`.
 */
export function useChatBackdropMotion({ surfaceRef, foregroundRef, hasBackdrop, windowActive }: UseChatBackdropMotionArgs) {
  const { backdropMotion } = useAppearancePrefs();
  const reducedMotion = useReducedMotion() ?? false;
  const parallaxRef = useRef<HTMLDivElement | null>(null);
  const enabled = hasBackdrop && backdropMotion && !reducedMotion;
  const parallaxActive = enabled && windowActive;

  useEffect(() => {
    const surface = surfaceRef.current;
    if (!parallaxActive || !surface) return undefined;
    const loop = createParallaxLoop({
      apply: (point) => {
        const transforms = parallaxTransforms(point);
        if (parallaxRef.current) parallaxRef.current.style.transform = transforms.backdrop;
        if (foregroundRef.current) foregroundRef.current.style.transform = transforms.foreground;
      },
    });
    const follow = (event: PointerEvent) => {
      loop.setTarget(parallaxTarget(event.clientX, event.clientY, surface.getBoundingClientRect()));
    };
    const recentre = () => loop.setTarget({ x: 0, y: 0 });
    surface.addEventListener("pointermove", follow);
    surface.addEventListener("pointerleave", recentre);
    return () => {
      surface.removeEventListener("pointermove", follow);
      surface.removeEventListener("pointerleave", recentre);
      loop.reset();
    };
  }, [foregroundRef, parallaxActive, surfaceRef]);

  return { parallaxRef, motion: enabled, paused: !windowActive };
}
