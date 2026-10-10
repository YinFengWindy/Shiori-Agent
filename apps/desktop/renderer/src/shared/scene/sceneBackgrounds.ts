import type { ScenePhase } from "./timeOfDay";

/**
 * Scene backgrounds of the desktop first-run guide and startup splash, one
 * per time-of-day phase (see `timeOfDay.ts`): a sakura street by day, a
 * rooftop at dusk, an arched-window bedroom under the moon at night. Purely
 * decorative (rendered with an empty alt).
 *
 * Resolved with `new URL(…, import.meta.url)` so the plain Node test runner
 * can load components that show them (Vite emits them as usual). The public
 * site (apps/site) imports the same files directly, as build-time assets.
 */
export const sceneBackgrounds: Record<ScenePhase, string> = {
  day: new URL("../assets/scene/bg-day.webp", import.meta.url).href,
  dusk: new URL("../assets/scene/bg-dusk.webp", import.meta.url).href,
  night: new URL("../assets/scene/bg-night.webp", import.meta.url).href,
};
