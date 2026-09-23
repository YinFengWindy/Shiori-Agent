import type { CSSProperties } from "react";

// Deterministic pseudo-random scatter (no `Math.random`, so the layout is
// stable across renders/screenshots): a simple irrational-step sequence
// gives an even, non-repeating-looking spread without a real RNG.
function scatter(count: number, seed: number): number[] {
  return Array.from({ length: count }, (_, i) => ((i + 1) * seed) % 1);
}

const STAR_LEFT = scatter(18, 0.6180339887);
const STAR_TOP = scatter(18, 0.3819660113);
const PETAL_LEFT = scatter(6, 0.7548776662);

/**
 * Purely decorative night-sky backdrop: a scatter of faint stars and sakura
 * petals over the title screen's gradient. Self-contained (not the shared
 * brand icon set, which the site does not depend on) and inert to assistive
 * tech. Looping drift/twinkle is disabled under prefers-reduced-motion, see
 * the `.site-decorations` rules in site.css.
 */
export function SiteDecorations() {
  return (
    <div className="site-decorations pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      {STAR_LEFT.map((left, i) => (
        <span
          key={`star-${i}`}
          className="site-decoration-star"
          style={{ "--i": i, left: `${left * 96}%`, top: `${STAR_TOP[i] * 88}%` } as CSSProperties}
        />
      ))}
      {PETAL_LEFT.map((left, i) => (
        <span key={`petal-${i}`} className="site-decoration-petal" style={{ "--i": i, left: `${left * 90}%` } as CSSProperties} />
      ))}
    </div>
  );
}
