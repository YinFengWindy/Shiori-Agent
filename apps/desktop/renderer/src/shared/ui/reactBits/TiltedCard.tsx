import { useEffect, useRef } from "react";
import type React from "react";
import { cx } from "../../styles";
import { canTilt, tiltFromPointer } from "../../tilt";

/**
 * Adapted from React Bits' TiltedCard component.
 * Source license: MIT + Commons Clause License Condition v1.0; see NOTICE.md.
 *
 * A hover-only 3D tilt with a moving glare band and a radial highlight that
 * follows the pointer. The pointer only writes CSS custom properties (once
 * per frame); the transform, the spring-back on leave (`--ease-spring`) and
 * the glare live in styles.css (`.tilt-card`). Mouse only: touch, pen, a
 * coarse pointer and reduced motion keep the card flat. The glare layers
 * ignore the pointer, so clicks, focus and menus inside behave as before.
 */
export function TiltedCard({
  children,
  className,
  maxDegrees = 8,
}: {
  children: React.ReactNode;
  className?: string;
  /** Lean at the card's edge, in degrees. */
  maxDegrees?: number;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const frameRef = useRef(0);
  const pointerRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => () => cancelAnimationFrame(frameRef.current), []);

  function applyFrame(): void {
    frameRef.current = 0;
    const card = ref.current;
    const pointer = pointerRef.current;
    if (!card || !pointer) return;
    const frame = tiltFromPointer(pointer, card.getBoundingClientRect(), maxDegrees);
    card.style.setProperty("--tilt-rx", `${frame.rotateX}deg`);
    card.style.setProperty("--tilt-ry", `${frame.rotateY}deg`);
    card.style.setProperty("--tilt-glare-x", `${frame.glareX}%`);
    card.style.setProperty("--tilt-mx", `${frame.highlightX}%`);
    card.style.setProperty("--tilt-my", `${frame.highlightY}%`);
  }

  function handlePointerEnter(event: React.PointerEvent<HTMLDivElement>): void {
    if (!canTilt(event.pointerType)) return;
    event.currentTarget.dataset.tilting = "true";
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>): void {
    if (event.currentTarget.dataset.tilting !== "true") return;
    pointerRef.current = { x: event.clientX, y: event.clientY };
    if (!frameRef.current) frameRef.current = requestAnimationFrame(applyFrame);
  }

  function handlePointerLeave(event: React.PointerEvent<HTMLDivElement>): void {
    cancelAnimationFrame(frameRef.current);
    frameRef.current = 0;
    pointerRef.current = null;
    const card = event.currentTarget;
    delete card.dataset.tilting;
    // Dropping the angles lets the CSS spring carry the card back to flat; the
    // glare keeps its last position so it fades out where it was.
    card.style.removeProperty("--tilt-rx");
    card.style.removeProperty("--tilt-ry");
  }

  return (
    <div
      ref={ref}
      className={cx("tilt-card relative", className)}
      onPointerEnter={handlePointerEnter}
      onPointerMove={handlePointerMove}
      onPointerLeave={handlePointerLeave}
    >
      {children}
      <span className="tilt-highlight" aria-hidden="true" />
      <span className="tilt-glare" aria-hidden="true" />
    </div>
  );
}
