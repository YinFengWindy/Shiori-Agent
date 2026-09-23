import type { CSSProperties } from "react";

// Deterministic pseudo-random scatter (no `Math.random`, so the layout is
// stable across renders/screenshots): a simple irrational-step sequence
// gives an even, non-repeating-looking spread without a real RNG.
function scatter(count: number, seed: number): number[] {
  return Array.from({ length: count }, (_, i) => ((i + 1) * seed) % 1);
}

const PETAL_LEFT = scatter(7, 0.7548776662);

/**
 * Purely decorative sakura petals drifting over the title screen's room
 * scene. Self-contained (not the shared brand icon set, which the site does
 * not depend on) and inert to assistive tech. The drift is switched off
 * under prefers-reduced-motion, see `.site-decoration-petal` in site.css.
 */
export function SiteDecorations() {
  return (
    <div className="site-decorations pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {PETAL_LEFT.map((left, i) => (
        <span key={i} className="site-decoration-petal" style={{ "--i": i, left: `${left * 90}%` } as CSSProperties} />
      ))}
    </div>
  );
}
