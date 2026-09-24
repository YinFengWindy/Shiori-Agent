/**
 * Whether the OS asks for reduced motion, read at the moment of use. For
 * imperative motion (scroll animations, scrollIntoView) that CSS media queries
 * and motion/react's MotionConfig cannot reach. False where matchMedia is
 * unavailable.
 */
export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
