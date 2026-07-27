import { useEffect, useRef, useState } from "react";
import type React from "react";

/**
 * Adapted from React Bits' Magnet component.
 * Source license: MIT + Commons Clause License Condition v1.0; see NOTICE.md.
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
  const [offset, setOffset] = useState({ x: 0, y: 0 });

  useEffect(() => {
    if (disabled) {
      setOffset({ x: 0, y: 0 });
      return;
    }

    function handlePointerMove(event: MouseEvent): void {
      const element = ref.current;
      if (!element) return;
      const rect = element.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const withinRange = Math.abs(event.clientX - centerX) < rect.width / 2 + padding
        && Math.abs(event.clientY - centerY) < rect.height / 2 + padding;
      setOffset(withinRange
        ? { x: (event.clientX - centerX) / strength, y: (event.clientY - centerY) / strength }
        : { x: 0, y: 0 });
    }

    window.addEventListener("mousemove", handlePointerMove);
    return () => window.removeEventListener("mousemove", handlePointerMove);
  }, [disabled, padding, strength]);

  return (
    <div ref={ref} className={className}>
      <div
        className="will-change-transform"
        style={{ transform: `translate3d(${offset.x}px, ${offset.y}px, 0)`, transition: "transform 320ms ease-out" }}
      >
        {children}
      </div>
    </div>
  );
}
