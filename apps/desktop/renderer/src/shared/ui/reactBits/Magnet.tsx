import { useReducedMotion } from "motion/react";
import { useEffect, useRef } from "react";
import type React from "react";

export type MagnetOffset = { x: number; y: number };

const restingOffset: MagnetOffset = { x: 0, y: 0 };

/** Where the magnet pulls its content for a pointer position; the resting offset when out of range. */
export function getMagnetOffset(
  pointer: { clientX: number; clientY: number },
  rect: { left: number; top: number; width: number; height: number },
  padding: number,
  strength: number,
): MagnetOffset {
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;
  const withinRange = Math.abs(pointer.clientX - centerX) < rect.width / 2 + padding
    && Math.abs(pointer.clientY - centerY) < rect.height / 2 + padding;
  return withinRange
    ? { x: (pointer.clientX - centerX) / strength, y: (pointer.clientY - centerY) / strength }
    : restingOffset;
}

/**
 * Adapted from React Bits' Magnet component.
 * Source license: MIT + Commons Clause License Condition v1.0; see NOTICE.md.
 *
 * The offset is written straight to the inner element's style rather than
 * kept in React state: the listener is window-wide, so a state update per
 * mousemove would re-render the wrapped subtree on every pointer move anywhere
 * in the app. A move that lands on the current offset (typically "still out
 * of range") touches nothing. Reduced motion turns the pull off.
 */
export function Magnet({
  children,
  disabled = false,
  padding = 72,
  strength = 7,
  className,
}: {
  children: React.ReactNode;
  disabled?: boolean;
  padding?: number;
  strength?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const innerRef = useRef<HTMLDivElement | null>(null);
  const offsetRef = useRef<MagnetOffset>(restingOffset);
  const reduceMotion = useReducedMotion();
  const inactive = disabled || Boolean(reduceMotion);

  useEffect(() => {
    function applyOffset(next: MagnetOffset): void {
      const current = offsetRef.current;
      if (next.x === current.x && next.y === current.y) return;
      offsetRef.current = next;
      if (innerRef.current) {
        innerRef.current.style.transform = `translate3d(${next.x}px, ${next.y}px, 0)`;
      }
    }

    if (inactive) {
      applyOffset(restingOffset);
      return undefined;
    }

    function handlePointerMove(event: MouseEvent): void {
      const element = ref.current;
      if (!element) return;
      applyOffset(getMagnetOffset(event, element.getBoundingClientRect(), padding, strength));
    }

    window.addEventListener("mousemove", handlePointerMove);
    return () => window.removeEventListener("mousemove", handlePointerMove);
  }, [inactive, padding, strength]);

  return (
    <div ref={ref} className={className}>
      <div
        ref={innerRef}
        className="will-change-transform"
        style={{ transform: "translate3d(0px, 0px, 0)", transition: "transform var(--duration-panel) var(--ease-out-soft)" }}
      >
        {children}
      </div>
    </div>
  );
}
