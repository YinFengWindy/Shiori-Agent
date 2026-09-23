import { useState } from "react";
import { useFrameTicker } from "../../hooks/useFrameTicker";
import { usePrefersReducedMotion } from "../../hooks/usePrefersReducedMotion";

/** Pause on the finished sample before it starts typing again. */
const HOLD_MS = 1200;

interface TextSpeedPreviewProps {
  text: string;
  msPerChar: number;
}

/**
 * A sample line typed out, on a loop, at the chosen speed. Remount it (key
 * on the speed) to restart from the first character; under reduced motion
 * it just shows the whole line.
 */
export function TextSpeedPreview({ text, msPerChar }: TextSpeedPreviewProps) {
  const reducedMotion = usePrefersReducedMotion();
  const [elapsedMs, setElapsedMs] = useState(0);
  const cycleMs = text.length * msPerChar + HOLD_MS;
  useFrameTicker(!reducedMotion, (delta) => setElapsedMs((current) => (current + delta) % cycleMs));

  const shown = reducedMotion ? text.length : Math.min(text.length, Math.floor(elapsedMs / msPerChar));
  return (
    <p className="site-settings-preview rounded-md text-body" aria-hidden="true">
      <span>{text.slice(0, shown)}</span>
      <span className="site-adv-text-pending">{text.slice(shown)}</span>
    </p>
  );
}
