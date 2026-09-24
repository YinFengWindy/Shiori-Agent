import { sceneBackgrounds } from "./sceneBackgrounds";
import type { ScenePhase } from "./timeOfDay";

/**
 * Full-bleed time-of-day scene: the phase's picture, cover-fitted and
 * unblurred, under a very light veil (styles in `shared/adv/adv.css`).
 * The caller picks the phase, and when to read the clock. Decorative only.
 */
export function SceneBackdrop({ phase }: { phase: ScenePhase }) {
  return (
    <div className="scene-backdrop pointer-events-none absolute inset-0" aria-hidden="true">
      <img src={sceneBackgrounds[phase]} alt="" className="scene-backdrop-image h-full w-full object-cover" />
      <div className="scene-backdrop-veil absolute inset-0" />
    </div>
  );
}
