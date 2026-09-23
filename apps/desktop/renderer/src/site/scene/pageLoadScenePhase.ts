import { scenePhaseAt } from "./timeOfDay";
import type { ScenePhase } from "./timeOfDay";

/**
 * The visitor's scene phase, read once when the site bundle loads: a visit
 * that crosses a phase boundary keeps its scene until the next page load.
 * Kept apart from the pure `timeOfDay.ts` so importing that has no clock read.
 */
export const pageLoadScenePhase: ScenePhase = scenePhaseAt(new Date());
