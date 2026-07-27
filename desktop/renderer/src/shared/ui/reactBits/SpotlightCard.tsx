import { useRef, useState } from "react";
import type React from "react";
import { cx } from "../../styles";

/**
 * Adapted from React Bits' SpotlightCard component.
 * Source license: MIT + Commons Clause License Condition v1.0; see NOTICE.md.
 */
export function SpotlightCard({
  children,
  className,
  spotlightColor = "rgba(255, 220, 190, 0.28)",
}: {
  children: React.ReactNode;
  className?: string;
  spotlightColor?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [visible, setVisible] = useState(false);

  function updatePosition(event: React.MouseEvent<HTMLDivElement>): void {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    setPosition({ x: event.clientX - rect.left, y: event.clientY - rect.top });
  }

  return (
    <div
      ref={ref}
      className={cx("relative overflow-hidden", className)}
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
      onMouseMove={updatePosition}
    >
      <div
        className="pointer-events-none absolute inset-0 transition-opacity duration-500"
        style={{
          opacity: visible ? 1 : 0,
          background: `radial-gradient(420px circle at ${position.x}px ${position.y}px, ${spotlightColor}, transparent 70%)`,
        }}
      />
      <div className="relative">{children}</div>
    </div>
  );
}
