import { motion, useReducedMotion, useSpring } from "motion/react";
import { useRef } from "react";
import type React from "react";

/**
 * Adapted from React Bits' TiltedCard component.
 * Source license: MIT + Commons Clause License Condition v1.0; see NOTICE.md.
 *
 * Under reduced motion the card stays flat: no tilt, no hover lift.
 */
export function TiltedCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement | null>(null);
  const reduceMotion = useReducedMotion();
  const rotateX = useSpring(0, { damping: 24, stiffness: 220, mass: 0.6 });
  const rotateY = useSpring(0, { damping: 24, stiffness: 220, mass: 0.6 });
  const scale = useSpring(1, { damping: 24, stiffness: 220, mass: 0.6 });

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>): void {
    if (reduceMotion) return;
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    const x = event.clientX - rect.left - rect.width / 2;
    const y = event.clientY - rect.top - rect.height / 2;
    rotateX.set((-y / (rect.height / 2)) * 5);
    rotateY.set((x / (rect.width / 2)) * 5);
  }

  return (
    <div className="[perspective:800px]" onPointerLeave={() => { rotateX.set(0); rotateY.set(0); scale.set(1); }} onPointerEnter={() => { if (!reduceMotion) scale.set(1.025); }} onPointerMove={handlePointerMove}>
      <motion.div ref={ref} className={className} style={{ rotateX, rotateY, scale, transformStyle: "preserve-3d" }}>
        {children}
      </motion.div>
    </div>
  );
}
